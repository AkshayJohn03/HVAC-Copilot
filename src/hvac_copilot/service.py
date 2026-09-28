"""HVACCopilot: the wiring facade (ingest -> index -> retrieve -> compose).

Owns the cross-cutting latency pack:

- **Exact query cache**: (normalised question, filters) -> Answer, LRU bounded.
- **Semantic cache**: past question embeddings compared by cosine; above the
  threshold the cached answer is reused (dev-grade embedder => conservative
  threshold). Cache hits short-circuit retrieval AND composition.
- **Per-stage timings**: understand/retrieve/compose milliseconds attached to
  every Answer.trace and recorded in the metrics registry.

Everything here is provider-agnostic: offline mocks by default, live
OpenAI-compatible endpoints via Settings.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from hvac_copilot.clients import build_clients
from hvac_copilot.config import Settings
from hvac_copilot.ingest.chunker import SectionAwareChunker
from hvac_copilot.ingest.indexer import IncrementalIndexer, IndexedSnapshot, IndexStats
from hvac_copilot.ingest.parser import parse_markdown_file
from hvac_copilot.qa.compose import AnswerComposer
from hvac_copilot.qa.multimodal import MultimodalQuery, PhotoQueryResult
from hvac_copilot.retrieve.hybrid import Filters, HybridRetriever, build_reranker
from hvac_copilot.retrieve.understand import QueryAnalyzer
from hvac_copilot.serve.metrics import MetricsRegistry

if TYPE_CHECKING:
    from hvac_copilot.qa.compose import Answer

SNAPSHOT_FILE = "index_snapshot.json"


class QueryCache:
    """Two-tier cache: exact key first, then semantic cosine match."""

    def __init__(self, maxsize: int = 256, semantic_threshold: float = 0.93) -> None:
        self.maxsize = maxsize
        self.semantic_threshold = semantic_threshold
        self._exact: OrderedDict[tuple, Answer] = OrderedDict()
        self._vectors: list[tuple[np.ndarray, tuple]] = []

    def _key(self, question: str, filters: Filters, top_k: int, mode: str = "hybrid") -> tuple:
        return (question.strip().lower(), filters.model_dump_json(), top_k, mode)

    def get(self, question: str, filters: Filters, top_k: int, embedder=None, mode: str = "hybrid") -> Answer | None:
        key = self._key(question, filters, top_k, mode)
        if key in self._exact:
            self._exact.move_to_end(key)
            answer = self._exact[key].model_copy(deep=True)
            answer.cache_hit = True
            return answer
        if embedder is not None and self._vectors:
            vec = np.asarray(embedder.embed([question])[0], dtype=np.float32)
            norm = float(np.linalg.norm(vec)) or 1.0
            vec = vec / norm
            for cached_vec, cached_key in self._vectors:
                if cached_key[1] == key[1] and cached_key[2] == key[2]:
                    if float(np.dot(vec, cached_vec)) >= self.semantic_threshold:
                        answer = self._exact[cached_key].model_copy(deep=True)
                        answer.cache_hit = True
                        return answer
        return None

    def put(self, question: str, filters: Filters, top_k: int, answer: Answer, embedder=None, mode: str = "hybrid") -> None:
        key = self._key(question, filters, top_k, mode)
        self._exact[key] = answer
        self._exact.move_to_end(key)
        while len(self._exact) > self.maxsize:
            old_key, _ = self._exact.popitem(last=False)
            self._vectors = [(v, k) for v, k in self._vectors if k != old_key]
        if embedder is not None:
            vec = np.asarray(embedder.embed([question])[0], dtype=np.float32)
            norm = float(np.linalg.norm(vec)) or 1.0
            self._vectors.append((vec / norm, key))
            if len(self._vectors) > self.maxsize:
                self._vectors = self._vectors[-self.maxsize :]

    def __len__(self) -> int:
        return len(self._exact)


class HVACCopilot:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()
        self.settings.ensure_dirs()
        self.metrics = MetricsRegistry()
        self.llm, self.vlm, self.embedder = build_clients(self.settings)
        self.reranker = build_reranker(self.settings.reranker)
        self.cache = QueryCache(
            maxsize=self.settings.query_cache_size,
            semantic_threshold=self.settings.semantic_cache_threshold,
        )
        self.snapshot: IndexedSnapshot | None = None
        self.analyzer = QueryAnalyzer(None)
        self.retriever: HybridRetriever | None = None
        self.composer = AnswerComposer(
            self.llm,
            None,  # attached after first ingest
            max_citations=self.settings.max_citations,
            guardrail_enabled=self.settings.guardrail_enabled,
        )
        self.multimodal: MultimodalQuery | None = None

    # -- ingest ---------------------------------------------------------------
    def ingest(self, corpus_dir: Path | None = None) -> IndexStats:
        """Parse -> chunk -> incremental index. Returns new/updated/unchanged stats."""
        corpus = Path(corpus_dir or self.settings.corpus_dir)
        chunker = SectionAwareChunker()
        chunks = []
        for md_file in sorted(corpus.glob("*.md")):
            doc = parse_markdown_file(md_file, md_file.name)
            chunks.extend(chunker.chunk_document(doc))
        # Fittable embedders (the hashed TF-IDF) learn their weighting from the
        # corpus; the fit digest invalidates the snapshot when the corpus changes.
        if hasattr(self.embedder, "fit"):
            self.embedder.fit([chunk.text for chunk in chunks])
        indexer = IncrementalIndexer(self.settings.index_dir / SNAPSHOT_FILE)
        self.snapshot, stats = indexer.index(chunks, self.embedder)
        self.retriever = HybridRetriever(
            self.snapshot,
            self.embedder,
            bm25_k1=self.settings.bm25_k1,
            bm25_b=self.settings.bm25_b,
            rrf_k=self.settings.rrf_k,
            pool_size=self.settings.pool_size,
        )
        self.analyzer.set_snapshot(self.snapshot)
        self.composer.retriever = self.retriever
        self.multimodal = MultimodalQuery(self.vlm, self.composer, self.retriever, self.analyzer)
        self.cache = QueryCache(  # index changed -> cached answers may be stale
            maxsize=self.settings.query_cache_size,
            semantic_threshold=self.settings.semantic_cache_threshold,
        )
        return stats

    def ensure_index(self) -> None:
        if self.retriever is None:
            self.ingest()

    # -- query ------------------------------------------------------------------
    async def ask(
        self,
        question: str,
        *,
        unit_model: str | None = None,
        top_k: int | None = None,
        safety: bool | None = None,
        mode: str = "hybrid",
    ) -> Answer:
        self.ensure_index()
        assert self.retriever is not None and self.snapshot is not None
        k = top_k or self.settings.top_k

        t0 = time.perf_counter()
        understanding = self.analyzer.analyze(question, context_unit=unit_model)
        understand_ms = (time.perf_counter() - t0) * 1000
        self.metrics.observe("understand", understand_ms)

        # The understood unit locks the metadata filter even when the caller
        # did not pass one explicitly (e.g. "the V9 chiller ...").
        effective_unit = unit_model or understanding.unit_model
        filters = Filters(unit_model=effective_unit, safety=safety)

        cached = self.cache.get(question, filters, k, self.embedder, mode=mode)
        if cached is not None:
            self.metrics.inc("hvac_cache_hits_total", help_doc="Query cache hits (exact + semantic)")
            self.metrics.inc("hvac_queries_total", help_doc="Queries handled")
            return cached

        t1 = time.perf_counter()
        retrieved = self.retriever.search(
            understanding.retrieval_query,
            filters=filters,
            top_k=k,
            mode=mode,
            reranker=self.reranker,
        )
        retrieve_ms = (time.perf_counter() - t1) * 1000
        self.metrics.observe("retrieve", retrieve_ms)

        t2 = time.perf_counter()
        answer = await self.composer.answer(question, understanding, retrieved)
        compose_ms = (time.perf_counter() - t2) * 1000
        self.metrics.observe("compose", compose_ms)
        answer.trace["timings_ms"] = {
            "understand": round(understand_ms, 2),
            "retrieve": round(retrieve_ms, 2),
            "compose": round(compose_ms, 2),
            "total": round((time.perf_counter() - t0) * 1000, 2),
        }

        if answer.escalation:
            self.metrics.inc(
                "hvac_guardrail_escalations_total", help_doc="Safety guardrail escalations"
            )
        self.metrics.inc("hvac_queries_total")
        self.cache.put(question, filters, k, answer, self.embedder, mode=mode)
        return answer

    async def ask_stream(self, question: str, **kwargs):
        """SSE-ready event dicts; mirrors ask() without the cache (streams are rare)."""
        self.ensure_index()
        assert self.retriever is not None
        understanding = self.analyzer.analyze(question, context_unit=kwargs.get("unit_model"))
        retrieved = self.retriever.search(
            understanding.retrieval_query,
            top_k=kwargs.get("top_k") or self.settings.top_k,
            reranker=self.reranker,
        )
        async for event in self.composer.stream(question, understanding, retrieved):
            yield event

    async def handle_photo(self, image_path: str | Path, question: str | None = None) -> PhotoQueryResult:
        self.ensure_index()
        assert self.multimodal is not None
        return await self.multimodal.handle_photo(image_path, question)

    # -- inspection ------------------------------------------------------------
    def health(self) -> dict:
        snapshot = self.snapshot
        return {
            "status": "ok",
            "indexed_chunks": len(snapshot.chunks) if snapshot else 0,
            "fault_codes": len(snapshot.fault_codes) if snapshot else 0,
            "embedding": snapshot.digest if snapshot else None,
            "llm_provider": self.settings.llm_provider,
            "cache_entries": len(self.cache),
        }
