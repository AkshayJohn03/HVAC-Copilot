"""Shared domain models (Chunk) used across ingest, retrieval and QA."""

from __future__ import annotations

import hashlib
import re
from typing import Any

from pydantic import BaseModel, Field


def content_hash(text: str) -> str:
    """Stable SHA-256 over normalised text. Whitespace-insensitive on purpose so
    cosmetic re-wraps of a manual do not invalidate embeddings."""
    normalised = re.sub(r"\s+", " ", text.strip().lower())
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


class Chunk(BaseModel):
    """The atomic retrieval unit.

    ``text`` is what gets embedded and indexed: it *includes* the breadcrumb
    context header, so every chunk carries its own place in the manual
    (unit > chapter > section) into lexical and vector space.
    """

    id: str
    text: str
    breadcrumb: list[str] = Field(default_factory=list)  # e.g. ["AriaTherm X200", "Fault Codes", ...]
    source_doc: str = ""  # corpus file name
    doc_type: str = "manual"
    unit_model: str | None = None  # "X200" | "V9"
    chunk_type: str = "section"  # section | table | steps | image
    safety: bool = False  # True => safety-critical chunk (guardrail support)
    table_id: str | None = None
    code_anchors: list[str] = Field(default_factory=list)  # fault codes anchored here
    # code -> {column -> value}; only for fault-code tables (whole-table chunks)
    row_registry: dict[str, dict[str, str]] = Field(default_factory=dict)
    image_ref: str | None = None
    caption: str | None = None
    page_hint: int | None = None  # PDF page number (None for markdown corpus)
    content_hash: str = ""

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            self.content_hash = content_hash(self.text)

    @property
    def section_path(self) -> str:
        """Breadcrumb without the unit prefix, used for citation rendering."""
        return " > ".join(self.breadcrumb[1:]) if len(self.breadcrumb) > 1 else (self.breadcrumb[0] if self.breadcrumb else "")

    def citation_label(self) -> str:
        label = " > ".join(self.breadcrumb) if self.breadcrumb else self.source_doc
        return f"{label} [{self.id}]"


class DirectHit(BaseModel):
    """Exact fault-code table row resolved without any fuzzy retrieval."""

    code: str
    unit_model: str | None = None
    chunk_ids: list[str] = Field(default_factory=list)
    rendered_row: str = ""
    row_data: dict[str, str] = Field(default_factory=dict)
