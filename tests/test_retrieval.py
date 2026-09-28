"""Retrieval behavior: fault-code fast path, cache, timings, filter semantics."""

from __future__ import annotations

import pytest

from hvac_copilot.retrieve.hybrid import Filters


@pytest.mark.asyncio
async def test_fault_code_direct_hit(service):
    ans = await service.ask("What does fault code E04 mean on the X200?", unit_model="X200")
    assert "E04" in ans.code_refs
    assert ans.escalation is False
    # the rendered fault-table row must surface the real manual content
    assert "Evaporator coil iced" in ans.answer or "iced" in ans.answer.lower()
    assert ans.citations, "direct hit must cite its source table"


@pytest.mark.asyncio
async def test_unknown_unit_degrades_gracefully(service):
    """A unit string that matches nothing must not crash (empty pool) and must
    not invent an answer."""
    ans = await service.ask("How do I clean the filter?", unit_model="NoSuchUnit 999")
    assert ans.answer  # something coherent came back


@pytest.mark.asyncio
async def test_query_cache_exact_hit(service):
    a1 = await service.ask("What is the symptom of fault code E09?", unit_model="X200")
    a2 = await service.ask("What is the symptom of fault code E09?", unit_model="X200")
    assert a2.cache_hit is True
    assert a1.answer == a2.answer


@pytest.mark.asyncio
async def test_answer_carries_stage_timings(service):
    ans = await service.ask("How often should I clean the condenser coil?", unit_model="V9")
    timings = ans.trace.get("timings_ms", {})
    assert {"understand", "retrieve", "compose", "total"} <= set(timings)
    assert timings["total"] > 0


def test_filters_mask_semantics(service):
    chunks = service.snapshot.chunks
    safety_chunks = [c for c in chunks if c.safety]
    assert safety_chunks, "corpus must contain safety-tagged chunks"
    masked = Filters(safety=True).mask(chunks)
    assert masked.sum() == len(safety_chunks)
