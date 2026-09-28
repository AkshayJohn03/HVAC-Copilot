"""Shared fixtures: one indexed service for the whole suite (offline, mocked)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from hvac_copilot.config import Settings  # noqa: E402
from hvac_copilot.service import HVACCopilot  # noqa: E402


@pytest.fixture(scope="session")
def service() -> HVACCopilot:
    """Indexed copilot over the committed corpus, tmp index dir, mocked clients."""
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        settings = Settings(index_dir=Path(td) / ".index")
        svc = HVACCopilot(settings)
        svc.ingest(REPO / "corpus")
        yield svc
