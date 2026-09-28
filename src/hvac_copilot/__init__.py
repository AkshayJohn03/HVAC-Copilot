"""HVAC-Copilot: multimodal document processor + grounded RAG assistant for HVAC field technicians.

The package is organised as a retrieval pipeline:

- ``ingest``  : markdown/PDF parsing, section-aware chunking, incremental indexing.
- ``retrieve``: query understanding (fault codes, slang, units) + hybrid BM25/dense search.
- ``qa``      : grounded answer composition with a safety guardrail + photo intake.
- ``serve``   : FastAPI surface (query, SSE stream, ingest, health, Prometheus metrics).
- ``eval``    : offline golden-set evaluation (recall, citation precision, groundedness).

Everything runs fully offline by default: the LLM/VLM/embedding clients sit behind
protocols with deterministic offline mocks, and heavy optional dependencies
(PyMuPDF, sentence-transformers, pytesseract, qdrant-client) are guarded imports.
"""

from hvac_copilot.config import Settings

__version__ = "0.1.0"

__all__ = ["Settings", "__version__"]
