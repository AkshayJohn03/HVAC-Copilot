"""Incremental indexing with content-hash change detection.

Re-embedding an unchanged manual is the classic RAG cost bug. Every chunk gets
a whitespace-insensitive SHA-256; on re-ingest, chunks whose hash matches the
persisted snapshot skip the embedder entirely. Stats report new / updated /
unchanged so the incrementality is observable (and tested).

Persistence: JSON snapshot by default (portable, diffable). A Qdrant-backed
store is available behind a guarded import for deployments that want the
vector store to own persistence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from hvac_copilot.models import Chunk

SNAPSHOT_VERSION = 1


@dataclass
class IndexStats:
    total_chunks: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0

    @property
    def re_embedded(self) -> int:
        return self.new + self.updated


@dataclass
class IndexedSnapshot:
    chunks: list[Chunk]
    matrix: np.ndarray  # (N, dim), row-aligned with chunks
    fault_codes: dict[str, list[str]] = field(default_factory=dict)
    digest: str = ""

    def code_lookup(self, code: str) -> list[Chunk]:
        ids = set(self.fault_codes.get(code.upper(), []))
        return [chunk for chunk in self.chunks if chunk.id in ids]


def embedding_digest(embedder) -> str:
    """Identity of the embedder: a snapshot from a different embedder is invalid.

    Includes the fit state (corpus-derived IDF table) when the embedder is
    fittable — a changed corpus changes the IDF table, which changes every
    vector, which must invalidate the snapshot.
    """
    provider = getattr(embedder, "provider", type(embedder).__name__)
    dim = getattr(embedder, "dim", "?")
    model = getattr(embedder, "model", "")
    fit_digest = getattr(embedder, "fit_digest", "")
    return f"{provider}:{model}:{dim}:{fit_digest}"


def build_fault_code_map(chunks: list[Chunk]) -> dict[str, list[str]]:
    registry: dict[str, list[str]] = {}
    for chunk in chunks:
        for code in chunk.code_anchors:
            registry.setdefault(code.upper(), []).append(chunk.id)
    return registry


class _SnapshotBackend:
    def save(self, path: Path, digest: str, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    def load(self, path: Path) -> tuple[str, dict[str, list[float]]] | None: ...


class JsonSnapshotStore:
    """Portable JSON snapshot: chunk metadata + vectors in one file."""

    def save(self, path: Path, digest: str, chunks: list[Chunk], vectors: np.ndarray) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": SNAPSHOT_VERSION,
            "digest": digest,
            "chunks": [
                {**chunk.model_dump(), "vector": vectors[i].tolist()}
                for i, chunk in enumerate(chunks)
            ],
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def load(self, path: Path) -> tuple[str, dict[str, list[float]]] | None:
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None  # corrupt snapshot -> treat as cold cache, not a crash
        if payload.get("version") != SNAPSHOT_VERSION:
            return None
        vectors = {
            entry["id"]: entry["vector"]
            for entry in payload.get("chunks", [])
            if "id" in entry and "vector" in entry
        }
        return payload.get("digest", ""), vectors


class QdrantSnapshotStore:
    """Qdrant-backed persistence (optional extra ``pip install hvac-copilot[qdrant]``).

    Vectors live in an in-memory Qdrant collection; metadata is mirrored in a
    small JSON file so snapshots stay human-inspectable.
    """

    def __init__(self) -> None:
        try:  # optional dependency: guarded import
            from qdrant_client import QdrantClient
            from qdrant_client import models as qmodels
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "index_backend='qdrant' requires the qdrant extra: pip install 'hvac-copilot[qdrant]'"
            ) from exc
        self._client = QdrantClient(":memory:")
        self._models = qmodels
        self._collection = "hvac_chunks"
        self._dim: int | None = None

    def save(self, path: Path, digest: str, chunks: list[Chunk], vectors: np.ndarray) -> None:
        qmodels = self._models
        self._dim = int(vectors.shape[1])
        if not self._client.collection_exists(self._collection):
            self._client.create_collection(
                self._collection, vectors_config=qmodels.VectorParams(size=self._dim, distance=qmodels.Distance.COSINE)
            )
        else:
            self._client.delete_collection(self._collection)
            self._client.create_collection(
                self._collection, vectors_config=qmodels.VectorParams(size=self._dim, distance=qmodels.Distance.COSINE)
            )
        self._client.upsert(
            self._collection,
            points=[
                qmodels.PointStruct(
                    id=abs(hash(chunk.id)) % (10**12),  # deterministic-enough positive int
                    vector=vectors[i].tolist(),
                    payload={"chunk_id": chunk.id, "content_hash": chunk.content_hash},
                )
                for i, chunk in enumerate(chunks)
            ],
        )
        # Metadata mirror keeps the snapshot diffable without Qdrant tooling.
        JsonSnapshotStore().save(path, digest, chunks, vectors)

    def load(self, path: Path) -> tuple[str, dict[str, list[float]]] | None:
        loaded = JsonSnapshotStore().load(path)
        if loaded is None:
            return None
        digest, by_id = loaded
        if self._client.collection_exists(self._collection) and self._dim:
            # Verify the vector store actually holds what the JSON mirror claims.
            count = self._client.count(self._collection).count
            if count != len(by_id):
                return None
        return digest, by_id


class IncrementalIndexer:
    def __init__(
        self,
        snapshot_path: Path,
        store: _SnapshotBackend | None = None,
    ) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.store = store or JsonSnapshotStore()

    def index(self, chunks: list[Chunk], embedder) -> tuple[IndexedSnapshot, IndexStats]:
        digest = embedding_digest(embedder)
        prior_digest, prior_vectors = self.store.load(self.snapshot_path) or ("", {})
        if prior_digest != digest:
            prior_vectors = {}  # embedder changed: everything re-embeds
        prior_ids = set(prior_vectors.keys())

        dim = getattr(embedder, "dim", None)
        if not dim and prior_vectors:
            dim = len(next(iter(prior_vectors.values())))
        if not dim:
            # Live embedders may not declare dim until first use; probe once.
            dim = len(embedder.embed(["probe"])[0])

        stats = IndexStats(total_chunks=len(chunks))
        vectors = np.zeros((len(chunks), dim), dtype=np.float32)
        to_embed: list[tuple[int, Chunk]] = []

        for i, chunk in enumerate(chunks):
            old = prior_vectors.get(chunk.id)
            if old is not None and len(old) == dim:
                vectors[i] = np.asarray(old, dtype=np.float32)
                stats.unchanged += 1
            else:
                to_embed.append((i, chunk))
                if chunk.id in prior_ids:
                    stats.updated += 1  # existed before, content changed
                else:
                    stats.new += 1

        if to_embed:
            embedded = embedder.embed([chunk.text for _, chunk in to_embed])
            for (i, _), vec in zip(to_embed, embedded, strict=True):
                vectors[i] = np.asarray(vec, dtype=np.float32)

        self.store.save(self.snapshot_path, digest, chunks, vectors)
        snapshot = IndexedSnapshot(
            chunks=chunks,
            matrix=vectors,
            fault_codes=build_fault_code_map(chunks),
            digest=digest,
        )
        return snapshot, stats
