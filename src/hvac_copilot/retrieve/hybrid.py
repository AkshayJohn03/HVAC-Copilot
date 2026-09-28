"""Hybrid retrieval: hand-rolled Okapi BM25 + dense vectors + Reciprocal Rank Fusion.

Why hybrid, and why RRF with k=60:

- BM25 is the precision backbone for manual text: exact fault codes, part
  numbers, and torque values are lexical objects; a dense-only system fumbles
  "E04" or "ATX-FLT-0501".
- The dense channel carries morphology and typos: "refrigerent" has near-zero
  BM25 mass against "refrigerant" but high char-n-gram overlap; field slang
  behaves the same way.
- RRF (score = sum 1/(k + rank), k=60) fuses the two rank lists without
  calibration: BM25 scores and cosine similarities live on incomparable scales,
  and a tuned linear mix would silently break when either corpus or embedder
  changes.

**The RRF-dilution caveat** (documented because we paid for it): RRF optimises
*recall robustness*, not top-1 precision. A noisy dense branch (typical of
dev-grade embedders) can drag lexically-wrong but superficially-similar
sections into the fused top ranks, diluting precision. Two mitigations ship:
the fault-code fast path removes exact-lookup traffic from fusion entirely,
and the Reranker protocol lets a cross-encoder rescue the fused pool when one
is configured. See README "Design decisions" for the measured effect.
"""

from __future__ import annotations

import math
import re
import time
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel, Field

from hvac_copilot.ingest.indexer import IndexedSnapshot
from hvac_copilot.models import Chunk

_TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i in is it its "
    "me my not of on or that the this to up was we what when where which who why "
    "will with you your do i".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed. Codes like 'e04' survive."""
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and len(t) > 1]


# Weight of the reranker's candidate-local score relative to the fused RRF
# score: final = rrf * (1 + RERANK_BLEND * rerank_norm). Tuned on the bundled
# golden set: 1.0 lets the reranker flip near-ties (summary row vs procedure
# body) without drowning the cross-branch RRF evidence.
RERANK_BLEND = 1.0


class Filters(BaseModel):
    unit_model: str | None = None
    doc_type: str | None = None
    safety: bool | None = None

    def mask(self, chunks: list[Chunk]) -> np.ndarray:
        mask = np.ones(len(chunks), dtype=bool)
        for i, chunk in enumerate(chunks):
            if self.unit_model and chunk.unit_model != self.unit_model:
                mask[i] = False
            if self.doc_type and chunk.doc_type != self.doc_type:
                mask[i] = False
            if self.safety is not None and chunk.safety != self.safety:
                mask[i] = False
        return mask


class ScoredChunk(BaseModel):
    chunk: Chunk
    scores: dict[str, float] = Field(default_factory=dict)
    rank: int | None = None


class BM25Index:
    """Okapi BM25 with smoothed Robertson-Sparck-Jones IDF, cached per snapshot."""

    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = docs_tokens
        self.doc_len = np.asarray([len(d) or 1 for d in docs_tokens], dtype=np.float64)
        self.avgdl = float(self.doc_len.mean()) if docs_tokens else 1.0
        self.n = len(docs_tokens)
        df: dict[str, int] = {}
        for tokens in docs_tokens:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        # Smoothed IDF: ln((N - df + 0.5) / (df + 0.5) + 1) — always positive.
        self.idf = {term: math.log((self.n - count + 0.5) / (count + 0.5) + 1.0) for term, count in df.items()}

    def scores(self, query_tokens: list[str], mask: np.ndarray | None = None) -> np.ndarray:
        result = np.zeros(self.n, dtype=np.float64)
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tokens in enumerate(self.docs):
                tf = tokens.count(term)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1.0 - self.b + self.b * self.doc_len[i] / self.avgdl)
                result[i] += idf * (tf * (self.k1 + 1.0)) / denom
        if mask is not None:
            result[~mask] = 0.0
        return result


# --- rerankers -----------------------------------------------------------------


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, items: list[ScoredChunk], top_k: int) -> list[ScoredChunk]: ...


class BM25Reranker:
    """Offline default: re-score the fused pool with a candidate-local BM25.

    Candidate-local IDF sharpens discrimination inside a small pool (common
    terms of the pool matter less), which measurably cleans up RRF dilution
    without any model download.
    """

    name = "bm25"

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b

    def rerank(self, query: str, items: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        if not items:
            return items
        mini = BM25Index([tokenize(item.chunk.text) for item in items], self.k1, self.b)
        raw = mini.scores(tokenize(query))
        rescored = [
            ScoredChunk(chunk=item.chunk, scores={**item.scores, "rerank": float(raw[i])})
            for i, item in enumerate(items)
        ]
        rescored.sort(key=lambda s: s.scores.get("rerank", 0.0), reverse=True)
        for rank, item in enumerate(rescored[:top_k], start=1):
            item.rank = rank
        return rescored[:top_k]


class CrossEncoderReranker:
    """Cross-encoder reranking via sentence-transformers (optional extra).

    Guarded import: constructed only when configured; raises an actionable
    error if the extra is missing. Never imported at module load time.
    """

    name = "cross-encoder"

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        try:  # optional dependency: guarded import
            from sentence_transformers import CrossEncoder
        except Exception as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "reranker='cross-encoder' requires the rerank extra: "
                "pip install 'hvac-copilot[rerank]'"
            ) from exc
        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, items: list[ScoredChunk], top_k: int) -> list[ScoredChunk]:
        if not items:
            return items
        pairs = [[query, item.chunk.text] for item in items]
        scores = self._model.predict(pairs)
        rescored = [
            ScoredChunk(chunk=item.chunk, scores={**item.scores, "rerank": float(scores[i])})
            for i, item in enumerate(items)
        ]
        rescored.sort(key=lambda s: s.scores["rerank"], reverse=True)
        for rank, item in enumerate(rescored[:top_k], start=1):
            item.rank = rank
        return rescored[:top_k]


def build_reranker(name: str) -> Reranker | None:
    if name == "bm25":
        return BM25Reranker()
    if name == "cross-encoder":
        return CrossEncoderReranker()
    if name == "none":
        return None
    raise ValueError(f"unknown reranker {name!r}")


def mmr_select(items: list[ScoredChunk], vectors: np.ndarray, top_k: int, lam: float) -> list[ScoredChunk]:
    """Maximal Marginal Relevance over the candidate pool's dense vectors."""
    if len(items) <= 1 or vectors.shape[0] <= 1:
        return items[:top_k]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms
    sim = unit @ unit.T
    selected: list[int] = [0]
    candidates = list(range(1, len(items)))
    while candidates and len(selected) < top_k:
        best, best_score = None, -math.inf
        for c in candidates:
            diversity = max((sim[c][s] for s in selected), default=0.0)
            score = lam * float(sim[c][selected[0]]) - (1 - lam) * diversity
            if score > best_score:
                best, best_score = c, score
        selected.append(best)  # type: ignore[arg-type]
        candidates.remove(best)  # type: ignore[arg-type]
    return [items[i] for i in selected[:top_k]]


class RetrievalResult(BaseModel):
    items: list[ScoredChunk]
    trace: dict = Field(default_factory=dict)

    @property
    def chunks(self) -> list[Chunk]:
        return [item.chunk for item in self.items]


class HybridRetriever:
    """BM25 + dense + RRF over an IndexedSnapshot. Immutable per snapshot."""

    def __init__(
        self,
        snapshot: IndexedSnapshot,
        embedder,
        *,
        bm25_k1: float = 1.5,
        bm25_b: float = 0.75,
        rrf_k: int = 60,
        pool_size: int = 50,
    ) -> None:
        self.snapshot = snapshot
        self.embedder = embedder
        self.rrf_k = rrf_k
        self.pool_size = pool_size
        self._bm25 = BM25Index(
            [tokenize(chunk.text) for chunk in snapshot.chunks], bm25_k1, bm25_b
        )
        matrix = np.asarray(snapshot.matrix, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        self._unit_matrix = matrix / norms  # cached normalised dense matrix
        self._row_of = {chunk.id: i for i, chunk in enumerate(snapshot.chunks)}

    # -- internals -----------------------------------------------------------
    def _dense_scores(self, query_text: str, mask: np.ndarray) -> np.ndarray:
        query_vec = np.asarray(self.embedder.embed([query_text])[0], dtype=np.float32)
        norm = float(np.linalg.norm(query_vec)) or 1.0
        sims = self._unit_matrix @ (query_vec / norm)
        sims[~mask] = -1.0
        return sims

    @staticmethod
    def _rrf_fuse(rank_lists: dict[str, list[int]], k: int) -> dict[int, float]:
        fused: dict[int, float] = {}
        for ranks in rank_lists.values():
            for r, doc_idx in enumerate(ranks, start=1):
                fused[doc_idx] = fused.get(doc_idx, 0.0) + 1.0 / (k + r)
        return fused

    # -- public ----------------------------------------------------------------
    def search(
        self,
        query: str,
        filters: Filters | None = None,
        *,
        top_k: int = 5,
        mode: str = "hybrid",  # hybrid | bm25 | dense
        reranker: Reranker | None = None,
        mmr_lambda: float = 0.0,
    ) -> RetrievalResult:
        started = time.perf_counter()
        chunks = self.snapshot.chunks
        mask = (filters or Filters()).mask(chunks)

        branch_scores: dict[str, dict[str, float]] = {}
        rank_lists: dict[str, list[int]] = {}

        bm25_raw = self._bm25.scores(tokenize(query), mask)
        bm25_order = np.argsort(-bm25_raw)[: self.pool_size]
        rank_lists["bm25"] = [int(i) for i in bm25_order if bm25_raw[i] > 0]
        branch_scores["bm25"] = {chunks[i].id: float(bm25_raw[i]) for i in rank_lists["bm25"]}

        if mode != "bm25":
            dense_raw = self._dense_scores(query, mask)
            dense_order = np.argsort(-dense_raw)[: self.pool_size]
            rank_lists["dense"] = [int(i) for i in dense_order if dense_raw[i] > 0.05]
            branch_scores["dense"] = {chunks[i].id: float(dense_raw[i]) for i in rank_lists["dense"]}

        fused = self._rrf_fuse(rank_lists, self.rrf_k)
        pool = sorted(fused, key=lambda i: fused[i], reverse=True)[: self.pool_size]
        branch_scores["rrf"] = {chunks[i].id: fused[i] for i in pool}

        items = [
            ScoredChunk(
                chunk=chunks[i],
                scores={
                    "bm25": branch_scores["bm25"].get(chunks[i].id, 0.0),
                    "dense": branch_scores.get("dense", {}).get(chunks[i].id, 0.0),
                    "rrf": fused[i],
                },
            )
            for i in pool
        ]

        if reranker is not None:
            # The reranker *adjusts* the fused order rather than replacing it:
            # final = rrf * (1 + 0.5 * rerank_norm). A pure re-sort would throw
            # away the cross-branch evidence RRF accumulated — and with a
            # lexical-only reranker that means the dense branch could never
            # influence the final order at all. Multiplicative fusion keeps
            # both signals (see README "Design decisions").
            rescored = reranker.rerank(query, items, top_k=len(items))
            rerank_scores = [s.scores.get("rerank", 0.0) for s in rescored]
            if rerank_scores:
                lo, hi = min(rerank_scores), max(rerank_scores)
                span = (hi - lo) or 1.0
                for s in rescored:
                    norm = (s.scores.get("rerank", 0.0) - lo) / span
                    s.scores["final"] = s.scores.get("rrf", 0.0) * (1.0 + RERANK_BLEND * norm)
                items = sorted(rescored, key=lambda s: s.scores["final"], reverse=True)
            # empty pool (no branch matched) falls through with items == []
        else:
            items = items[:top_k]

        if mmr_lambda > 0.0 and mode != "bm25" and len(items) > 1:
            idx = [self._row_of[item.chunk.id] for item in items]
            items = mmr_select(items, self._unit_matrix[idx], top_k, mmr_lambda)

        for rank, item in enumerate(items, start=1):
            item.rank = rank

        elapsed_ms = (time.perf_counter() - started) * 1000
        trace = {
            "branches": branch_scores,
            "rrf_k": self.rrf_k,
            "mode": mode,
            "pool_size": len(pool),
            "retrieve_ms": round(elapsed_ms, 2),
        }
        return RetrievalResult(items=items, trace=trace)

    # -- safety support lookups -------------------------------------------------
    def chunk_by_id(self, chunk_id: str) -> Chunk | None:
        row = self._row_of.get(chunk_id)
        return self.snapshot.chunks[row] if row is not None else None

    def safety_chunks(self, unit_model: str | None = None) -> list[Chunk]:
        return [
            chunk
            for chunk in self.snapshot.chunks
            if chunk.safety and (unit_model is None or chunk.unit_model == unit_model)
        ]

    def nearest_safety_chunk(self, query: str, unit_model: str | None = None) -> Chunk | None:
        """Lexically nearest safety chunk — cited by the guardrail on escalation."""
        safety = self.safety_chunks(unit_model) or self.safety_chunks(None)
        if not safety:
            return None
        q_tokens = set(tokenize(query))

        def overlap(chunk: Chunk) -> int:
            return len(q_tokens & set(tokenize(chunk.text)))

        return max(safety, key=overlap)
