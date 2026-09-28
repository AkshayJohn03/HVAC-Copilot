"""Grounded answer composition with the safety guardrail.

The composer owns two non-negotiable behaviours:

1. **Grounding**: the prompt carries only retrieved chunks (plus exact
   fault-code rows); the system prompt demands section citations and forbids
   invention. Citations returned to the caller are derived from what the
   answer actually used (explicit [Ci] markers, else lexical overlap), so
   citation precision is measurable.

2. **Safety escalation (grounded refusal)**: if the query OR the retrieved
   context touches refrigerant / pressurised / energised-electrical / gas
   topics and *no* retrieved chunk is tagged ``safety=true``, the composer does
   not call the LLM at all. It answers with an escalation message, cites the
   nearest indexed safety section, and flags a supervisor review.

   Why retrieval-grounded refusal beats model refusal: a model asked to "be
   careful" can be talked into procedure-by-procedure leakage, and its refusal
   is unverifiable. A refusal that is *computed from retrieval state* is
   deterministic, unit-testable, and auditable — the guardrail fires on the
   absence of safety documentation, not on the model's opinion of risk.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from pydantic import BaseModel, Field

from hvac_copilot.clients.base import LLMClient, Message
from hvac_copilot.models import Chunk, DirectHit
from hvac_copilot.retrieve.hybrid import RetrievalResult, ScoredChunk, tokenize
from hvac_copilot.retrieve.understand import QueryUnderstanding
from hvac_copilot.safety_policy import detect_safety_topics, escalation_message, is_procedural

_CITATION_MARKER = re.compile(r"\[C(\d+)\]")
_WORD = re.compile(r"[a-z0-9]+")
_SENT_RE = re.compile(r"(?<=[.!?])\s+|\n")

SYSTEM_PROMPT = """You are an HVAC service documentation assistant for field technicians.
Rules:
1. Answer ONLY from the provided context. Quote numbers (torques, pressures, part numbers) exactly as written.
2. Cite the context blocks you use as [C1], [C2], ... after the sentences they support.
3. If the context does not contain the answer, say what is missing instead of guessing.
4. For safety-critical work (refrigerant, pressurised systems, live electrical), never expand on procedures: point to the safety section and recommend a certified technician.
"""


class Citation(BaseModel):
    chunk_id: str
    source_doc: str
    section_path: str
    breadcrumb: list[str]
    safety: bool = False
    quote: str | None = None
    caption: str | None = None
    code_anchors: list[str] = Field(default_factory=list)
    image_ref: str | None = None
    page_hint: int | None = None


class Answer(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    code_refs: list[str] = Field(default_factory=list)
    escalation: bool = False
    escalation_topics: list[str] = Field(default_factory=list)
    diagram_refs: list[str] = Field(default_factory=list)
    page_refs: list[int] = Field(default_factory=list)
    trace: dict = Field(default_factory=dict)
    cache_hit: bool = False


def _content_tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if len(t) > 2}


class AnswerComposer:
    def __init__(
        self,
        llm: LLMClient,
        retriever,  # HybridRetriever; typed loosely to avoid a circular import
        *,
        max_citations: int = 4,
        guardrail_enabled: bool = True,
        max_context_chars: int = 1400,
    ) -> None:
        self.llm = llm
        self.retriever = retriever
        self.max_citations = max_citations
        self.guardrail_enabled = guardrail_enabled
        self.max_context_chars = max_context_chars

    # -- guardrail ------------------------------------------------------------
    _PROCEDURAL_ASK = re.compile(
        r"\b(how (do|to|should|can)|can i|steps|procedure|what should i do|"
        r"is it (safe|ok|okay)|safe to|allowable|correct way)\b",
        re.IGNORECASE,
    )

    @staticmethod
    def _quote_candidates(chunk: Chunk, question: str, max_sentences: int = 4) -> list[str]:
        """Sentences of ``chunk`` that share vocabulary with the question —
        i.e. what an extractive answer would actually quote from it."""
        q_tokens = _content_tokens(question)
        scored = []
        for sentence in _SENT_RE.split(chunk.text):
            tokens = _content_tokens(sentence)
            if not tokens:
                continue
            overlap = len(q_tokens & tokens)
            if overlap:
                scored.append((overlap, sentence.strip()))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [s for _, s in scored[:max_sentences]]

    def guardrail_decision(
        self,
        question: str,
        retrieved: RetrievalResult,
        has_direct_hits: bool = False,
    ) -> tuple[bool, list[str]]:
        """Returns (should_escalate, topics).

        Escalation fires when the question itself is hazardous (query topics)
        or when a procedural-seeking question would be answered from
        hazard-bearing material — approximated by scanning the sentences of
        the primary (rank-1) chunk that the answer would actually quote. Two
        exemptions, both documented:

        - Definition lookups with a validated fault-code direct hit answer
          from the manual's own table row — no synthesis happens.
        - Non-procedural questions ("how much charge does the unit carry")
          are spec lookups even when hazardous nouns appear in context.

        Scanning whole context chunks produced false escalations on benign
        procedures whose *neighbours* mention hazards (a maintenance schedule
        row, a cross-reference); the quote-candidate window fixes that. See
        README "Design decisions" -> "Safety escalation".
        """
        if not self.guardrail_enabled:
            return False, []
        if has_direct_hits:
            return False, []
        procedural_intent = bool(self._PROCEDURAL_ASK.search(question))
        query_topics = set(detect_safety_topics(question))

        content_topics: set[str] = set()
        if procedural_intent and retrieved.items:
            primary = retrieved.items[0].chunk
            for sentence in self._quote_candidates(primary, question):
                content_topics.update(detect_safety_topics(sentence))

        topics = query_topics | content_topics
        support = any(item.chunk.safety for item in retrieved.items[:8])
        if not topics:
            return False, []
        if not (query_topics or procedural_intent):
            return False, []  # informational lookup; no synthesis risk
        return (not support), sorted(topics)

    def _escalation_answer(
        self, question: str, topics: list[str], understanding: QueryUnderstanding
    ) -> Answer:
        nearest = self.retriever.nearest_safety_chunk(question, understanding.unit_model)
        section = nearest.section_path if nearest else None
        text = escalation_message(topics, section, understanding.unit_model)
        citations = (
            [
                Citation(
                    chunk_id=nearest.id,
                    source_doc=nearest.source_doc,
                    section_path=nearest.section_path,
                    breadcrumb=nearest.breadcrumb,
                    safety=True,
                )
            ]
            if nearest
            else []
        )
        return Answer(
            question=question,
            answer=text,
            citations=citations,
            escalation=True,
            escalation_topics=topics,
            trace={"guardrail": "escalated", "topics": topics},
        )

    # -- prompt -----------------------------------------------------------------
    @staticmethod
    def _direct_hit_block(hit: DirectHit) -> str:
        unit = f" ({hit.unit_model})" if hit.unit_model else ""
        return f"[EXACT MATCH {hit.code}{unit}] {hit.rendered_row}"

    def _build_messages(
        self, question: str, understanding: QueryUnderstanding, retrieved: RetrievalResult
    ) -> tuple[list[Message], list[Chunk]]:
        blocks: list[str] = []
        ordered: list[Chunk] = []
        for hit in understanding.direct_hits:
            blocks.append(self._direct_hit_block(hit))
            ordered.append(Chunk(id=f"direct:{hit.code}", text=hit.rendered_row, source_doc="fault-table", breadcrumb=["Fault Codes"], code_anchors=[hit.code]))  # pseudo-chunk for citation mapping
        for item in retrieved.items:
            if len(blocks) >= 8:
                break
            blocks.append(f"[C{len(ordered) + 1}] {' > '.join(item.chunk.breadcrumb)}\n{item.chunk.text[: self.max_context_chars]}")
            ordered.append(item.chunk)

        context = "DIRECT TABLE LOOKUPS:\n" + "\n".join(
            b for b in blocks if b.startswith("[EXACT MATCH")
        ) if any(b.startswith("[EXACT MATCH") for b in blocks) else ""
        regular = "\n\n".join(b for b in blocks if not b.startswith("[EXACT MATCH"))
        user = f"QUESTION: {question}\n\n{context}\n\n{regular}".strip()
        messages = [Message(role="system", content=SYSTEM_PROMPT), Message(role="user", content=user)]
        return messages, ordered

    # -- citations ----------------------------------------------------------------
    def _direct_citations(self, understanding: QueryUnderstanding) -> list[Citation]:
        """Citations for exact fault-code hits: the authoritative table chunks."""
        citations: list[Citation] = []
        for hit in understanding.direct_hits:
            for chunk_id in hit.chunk_ids:
                chunk = self.retriever.chunk_by_id(chunk_id) if self.retriever else None
                if chunk is None:
                    continue
                citations.append(
                    Citation(
                        chunk_id=chunk.id,
                        source_doc=chunk.source_doc,
                        section_path=chunk.section_path,
                        breadcrumb=chunk.breadcrumb,
                        safety=chunk.safety,
                        caption=chunk.caption,
                        code_anchors=list(chunk.code_anchors),
                    )
                )
        return citations

    def _derive_citations(self, answer_text: str, ordered: list[Chunk]) -> list[Citation]:
        """Cite chunks the answer actually used: explicit markers first, then overlap."""
        picked: list[Chunk] = []
        for num in _CITATION_MARKER.findall(answer_text):
            idx = int(num) - 1
            if 0 <= idx < len(ordered) and not any(c.id == ordered[idx].id for c in picked):
                picked.append(ordered[idx])
        if not picked:
            answer_tokens = _content_tokens(answer_text)
            scored = []
            for chunk in ordered:
                if chunk.id.startswith("direct:"):
                    continue
                # Coverage relative to the ANSWER: a chunk is cited when it
                # accounts for the bulk of what the answer actually says.
                coverage = len(answer_tokens & _content_tokens(chunk.text)) / max(len(answer_tokens), 1)
                scored.append((coverage, chunk))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            picked = [chunk for coverage, chunk in scored if coverage >= 0.6][: self.max_citations]
            if not picked and scored and scored[0][0] > 0:
                picked = [scored[0][1]]
            if not picked:
                first_regular = next((c for c in ordered if not c.id.startswith("direct:")), None)
                picked = [first_regular] if first_regular else []
        return [
            Citation(
                chunk_id=chunk.id,
                source_doc=chunk.source_doc,
                section_path=chunk.section_path,
                breadcrumb=chunk.breadcrumb,
                safety=chunk.safety,
                caption=chunk.caption,
                code_anchors=list(chunk.code_anchors),
                image_ref=chunk.image_ref,
                page_hint=chunk.page_hint,
            )
            for chunk in picked[: self.max_citations]
        ]

    def _with_nearest_safety_citation(self, question, understanding, citations):
        """Safety-topic queries always carry a safety-tagged citation: if fusion
        ranked the safety chapter below the cutoff, pull it directly."""
        from ..safety_policy import detect_safety_topics

        if self.retriever is None or not citations and not understanding.direct_hits:
            if not detect_safety_topics(question):
                return citations
        if not detect_safety_topics(question) or any(c.safety for c in citations):
            return citations
        try:
            from ..retrieve.hybrid import Filters

            safe = self.retriever.search(
                understanding.retrieval_query,
                filters=Filters(safety=True),
                top_k=1,
                mode="bm25",
                reranker=None,
            )
            if safe.items:
                sc = safe.items[0].chunk
                if sc.id not in {c.chunk_id for c in citations}:
                    citations.append(
                        Citation(
                            chunk_id=sc.id,
                            source_doc=sc.source_doc,
                            section_path=sc.section_path,
                            breadcrumb=sc.breadcrumb,
                            safety=True,
                            caption=sc.caption,
                            code_anchors=list(sc.code_anchors),
                            image_ref=sc.image_ref,
                            page_hint=sc.page_hint,
                        )
                    )
        except Exception:
            pass  # boost is best-effort; the primary citations stand
        return citations

    # -- answer --------------------------------------------------------------------
    async def answer(
        self, question: str, understanding: QueryUnderstanding, retrieved: RetrievalResult
    ) -> Answer:
        escalate, topics = self.guardrail_decision(
            question, retrieved, has_direct_hits=bool(understanding.direct_hits)
        )
        if escalate:
            return self._escalation_answer(question, topics, understanding)

        messages, ordered = self._build_messages(question, understanding, retrieved)
        text = await self.llm.complete(messages)
        if understanding.direct_hits:
            # Exact-match rows are rendered deterministically above the LLM text:
            # a fault-code lookup must surface the manual's row verbatim, never a
            # paraphrase of it.
            rows = chr(10).join(f"- {hit.rendered_row}" for hit in understanding.direct_hits)
            text = "Exact match from the fault-code table:" + chr(10) + rows + chr(10) + chr(10) + text
        direct_citations = self._direct_citations(understanding)
        citations = direct_citations or self._derive_citations(text, ordered)
        citations = self._with_nearest_safety_citation(question, understanding, citations)
        citations = citations[: max(self.max_citations, len(citations))]
        diagram_refs = sorted({c.image_ref for c in citations if c.image_ref})
        page_refs = sorted({c.page_hint for c in citations if c.page_hint is not None})
        return Answer(
            question=question,
            answer=text,
            citations=citations,
            code_refs=list(understanding.codes),
            escalation=False,
            diagram_refs=diagram_refs,
            page_refs=page_refs,
            trace={
                "guardrail": "pass",
                "retrieval": retrieved.trace,
                "understanding": understanding.model_dump(exclude={"direct_hits"}),
            },
        )

    # -- streaming -------------------------------------------------------------------
    async def stream(
        self, question: str, understanding: QueryUnderstanding, retrieved: RetrievalResult
    ) -> AsyncIterator[dict]:
        """SSE-ready events: {'event': meta|token|done, 'data': ...}."""
        yield {"event": "meta", "data": understanding.model_dump(exclude={"direct_hits"})}

        escalate, topics = self.guardrail_decision(
            question, retrieved, has_direct_hits=bool(understanding.direct_hits)
        )
        if escalate:
            answer = self._escalation_answer(question, topics, understanding)
            for token in answer.answer.split(" "):
                yield {"event": "token", "data": token + " "}
            answer.trace["retrieval"] = retrieved.trace
            yield {"event": "done", "data": answer.model_dump()}
            return

        messages, ordered = self._build_messages(question, understanding, retrieved)
        pieces: list[str] = []
        async for token in self.llm.stream(messages):
            pieces.append(token)
            yield {"event": "token", "data": token}
        text = "".join(pieces).strip()
        citations = self._direct_citations(understanding) or self._derive_citations(text, ordered)
        citations = citations[: self.max_citations]
        answer = Answer(
            question=question,
            answer=text,
            citations=citations,
            code_refs=list(understanding.codes),
            diagram_refs=sorted({c.image_ref for c in citations if c.image_ref}),
            page_refs=sorted({c.page_hint for c in citations if c.page_hint is not None}),
            trace={"guardrail": "pass", "retrieval": retrieved.trace},
        )
        yield {"event": "done", "data": answer.model_dump()}


# eval helper re-export: the runner checks procedural leakage without a composer
def answer_is_procedural(text: str) -> bool:
    return is_procedural(text)


def overlap_score(a: str, b: str) -> float:
    """Jaccard-style token overlap used by eval + citation fallback."""
    ta, tb = set(tokenize(a)), set(tokenize(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


__all__ = ["Answer", "AnswerComposer", "Citation", "answer_is_procedural", "overlap_score", "ScoredChunk"]
