"""Ingest pipeline: parse -> chunk -> index (markdown by default, PDF upgrade)."""

from hvac_copilot.ingest.chunker import SectionAwareChunker
from hvac_copilot.ingest.indexer import (
    IncrementalIndexer,
    IndexedSnapshot,
    IndexStats,
    JsonSnapshotStore,
)
from hvac_copilot.ingest.parser import ParsedDocument, parse_markdown, parse_markdown_file

__all__ = [
    "IncrementalIndexer",
    "IndexedSnapshot",
    "IndexStats",
    "JsonSnapshotStore",
    "ParsedDocument",
    "SectionAwareChunker",
    "parse_markdown",
    "parse_markdown_file",
]
