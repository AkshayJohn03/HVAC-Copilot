"""PDF ingestion (optional upgrade path).

The bundled corpus is markdown, so the default pipeline never needs PyMuPDF.
When the ``pdf`` extra is installed (``pip install hvac-copilot[pdf]``) this
module upgrades ingestion to real PDFs: per-page text plus rendered page
images that the VLM path can caption (wiring diagrams, exploded views).

Guarded import with a graceful, actionable failure -- never a traceback leak.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:  # optional dependency: guarded import
    import fitz  # PyMuPDF

    HAS_PYMUPDF = True
    _IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover - depends on environment
    fitz = None  # type: ignore[assignment]
    HAS_PYMUPDF = False
    _IMPORT_ERROR = exc


class PdfNotAvailable(RuntimeError):
    """Raised when PDF parsing is requested without the PyMuPDF extra."""


@dataclass(frozen=True)
class PdfPage:
    number: int  # 1-based
    text: str


class PdfPageParser:
    """PyMuPDF-backed page parser + page-image extractor."""

    def __init__(self, image_dpi: int = 120) -> None:
        self.image_dpi = image_dpi

    @staticmethod
    def is_available() -> bool:
        return HAS_PYMUPDF

    def _require(self) -> None:
        if not HAS_PYMUPDF:
            hint = "pip install 'hvac-copilot[pdf]'"
            if _IMPORT_ERROR is not None:
                raise PdfNotAvailable(
                    f"PyMuPDF is required for PDF ingestion ({hint}); import failed: {_IMPORT_ERROR}"
                )
            raise PdfNotAvailable(f"PyMuPDF is required for PDF ingestion ({hint})")

    def parse(self, path: str | Path) -> list[PdfPage]:
        """Extract per-page text (1-based page numbers kept for citations)."""
        self._require()
        pages: list[PdfPage] = []
        with fitz.open(str(path)) as doc:  # type: ignore[union-attr]
            for zero_based, page in enumerate(doc):
                pages.append(PdfPage(number=zero_based + 1, text=page.get_text("text")))
        return pages

    def extract_page_images(self, path: str | Path, out_dir: str | Path) -> list[Path]:
        """Render each page to PNG for the VLM captioning path."""
        self._require()
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        with fitz.open(str(path)) as doc:  # type: ignore[union-attr]
            for zero_based, page in enumerate(doc):
                pix = page.get_pixmap(dpi=self.image_dpi)
                target = out / f"{Path(path).stem}_p{zero_based + 1:03d}.png"
                pix.save(str(target))
                written.append(target)
        return written
