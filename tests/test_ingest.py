"""Ingest: incremental indexing, chunking invariants, corpus determinism."""

from __future__ import annotations

import hashlib
from pathlib import Path

from hvac_copilot.config import Settings
from hvac_copilot.service import HVACCopilot

REPO = Path(__file__).resolve().parents[1]


def test_incremental_reingest_skips_unchanged(tmp_path):
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        svc = HVACCopilot(Settings(index_dir=Path(td) / ".index"))
        first = svc.ingest(REPO / "corpus")
        assert first.new > 0
        second = svc.ingest(REPO / "corpus")
        assert second.new == 0 and second.updated == 0
        assert second.unchanged == first.total_chunks


def test_fault_table_chunk_kept_whole(service):
    """The fault-code summary table must be ONE chunk (rows co-located), so a
    code lookup never loses its row context."""
    tables = [
        c
        for c in service.snapshot.chunks
        if c.id.endswith("table") and "E04" in c.text and "E01" in c.text
    ]
    assert tables, "fault-code summary table must be a single whole chunk"


def test_safety_chunks_tagged(service):
    refrigerant = [c for c in service.snapshot.chunks if c.safety and "refrigerant" in c.text.lower()]
    assert refrigerant, "refrigerant-handling sections must carry safety=True"


def test_corpus_build_is_deterministic():
    """Same generator, two runs -> byte-identical chapter contents."""
    import hvac_copilot.scripts.build_corpus as bc

    def digest():

        return {
            name: hashlib.sha256(content.encode("utf-8")).hexdigest()
            for name, content in bc.build_all()
        }

    ha, hb = digest(), digest()
    assert ha == hb, "corpus generator must be deterministic"
    assert len(ha) >= 15, "corpus must be substantive (15 chapters)"
