"""Section-aware hierarchical chunking for HVAC manuals.

Why not fixed-size chunking: manuals are *structured* documents. A fault-code
table split across two chunks becomes unretrievable as a unit; a safety notice
buried inside a generic chunk loses the flag the guardrail depends on; a
procedure sliced mid-step produces answers that skip the step where the danger
lives. This chunker therefore walks the heading tree and emits:

- section chunks  (unit > chapter > section hierarchy as a breadcrumb header)
- step-group chunks for numbered procedures (grouped, never split mid-step)
- whole-table chunks (caption + code anchors; never split)
- image-reference chunks (caption lifted from adjacent text for VLM captioning)

Every chunk's ``text`` starts with its breadcrumb header so the hierarchical
context is present in both the lexical and the vector index ("overlapping
context header": the shared prefix is exactly what sibling chunks have in
common, which keeps neighbourhood queries coherent).
"""

from __future__ import annotations

import re

from hvac_copilot.ingest.parser import ParsedDocument, ParsedSection
from hvac_copilot.models import Chunk

UNIT_DISPLAY = {"X200": "AriaTherm X200", "V9": "VeyraCool V9"}

_STEP_LINE = re.compile(r"^\s*(\d+)[.)]\s+(.+)$", re.MULTILINE)
_ANY_CODE = re.compile(r"\bE\s?-?(\d{2,3})\b")
_WARN_LINE = re.compile(r"(DANGER|WARNING)\s*[:!-]", re.IGNORECASE)


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "x"


def _codes_in(text: str) -> list[str]:
    return sorted({f"E{m.group(1)}" for m in _ANY_CODE.finditer(text)})


class SectionAwareChunker:
    def __init__(
        self,
        min_body_chars: int = 30,
        max_chunk_chars: int = 1800,
        step_group_size: int = 4,
        min_steps_for_procedure: int = 5,
    ) -> None:
        self.min_body_chars = min_body_chars
        self.max_chunk_chars = max_chunk_chars
        self.step_group_size = step_group_size
        self.min_steps_for_procedure = min_steps_for_procedure

    # -- public ---------------------------------------------------------------
    def chunk_document(self, doc: ParsedDocument) -> list[Chunk]:
        # Root of every breadcrumb is the chapter title (H1) — it carries the
        # chapter-level topic ("— Fault Codes", "— Electrical Wiring",
        # "— Refrigerant Handling Safety") that section titles alone lack.
        root = doc.title or UNIT_DISPLAY.get(doc.unit_model or "", doc.source_doc)
        chunks: list[Chunk] = []
        for section in doc.sections:
            self._walk(section, [root], doc, chunks)
        return chunks

    # -- internals --------------------------------------------------------------
    def _walk(
        self,
        section: ParsedSection,
        breadcrumb: list[str],
        doc: ParsedDocument,
        chunks: list[Chunk],
    ) -> None:
        path = [*breadcrumb, section.title]
        base_meta = {
            "source_doc": doc.source_doc,
            "doc_type": doc.doc_type,
            "unit_model": doc.unit_model,
        }

        # 1) Section body (or procedure step groups).
        self._emit_body_chunks(section, path, base_meta, chunks, doc)

        # 2) Tables stay whole.
        for table in section.tables:
            header = f"[Table] {table.caption}" if table.caption else "[Table]"
            text = f"{header}\n\n{table.raw_markdown}"
            chunks.append(
                Chunk(
                    id=self._chunk_id(doc.source_doc, path, "table"),
                    text=text,
                    breadcrumb=[*breadcrumb, section.title],
                    chunk_type="table",
                    table_id=table.table_id,
                    code_anchors=sorted(table.row_data.keys()) if table.row_data else _codes_in(text),
                    row_registry=table.row_data,
                    caption=table.caption,
                    safety=section.safety or bool(_WARN_LINE.search(text)),
                    **base_meta,
                )
            )

        # 3) Image references become addressable chunks (VLM captioning optional).
        for image in section.images:
            caption = image.caption or image.alt or "Figure (caption unavailable)"
            text = f"[Figure] {caption} (asset: {image.src})"
            chunks.append(
                Chunk(
                    id=self._chunk_id(doc.source_doc, path, "image"),
                    text=text,
                    breadcrumb=[*breadcrumb, section.title],
                    chunk_type="image",
                    caption=caption,
                    image_ref=image.src,
                    safety=section.safety or bool(_WARN_LINE.search(text)),
                    **base_meta,
                )
            )

        for child in section.children:
            self._walk(child, path, doc, chunks)

    def _emit_body_chunks(
        self,
        section: ParsedSection,
        path: list[str],
        base_meta: dict,
        chunks: list[Chunk],
        doc: ParsedDocument,
    ) -> None:
        text = section.text
        if not text or len(text.strip()) < self.min_body_chars:
            return

        steps = _STEP_LINE.findall(text)
        if len(steps) >= self.min_steps_for_procedure:
            self._emit_step_groups(section, path, base_meta, text, chunks, doc)
            return

        for ordinal, part in enumerate(self._split_long(text)):
            chunks.append(
                Chunk(
                    id=self._chunk_id(doc.source_doc, path, "sec", ordinal or None),
                    text=f"[{' > '.join(path)}]\n\n{part.strip()}",
                    breadcrumb=list(path),
                    chunk_type="section",
                    code_anchors=_codes_in(part),
                    safety=section.safety or bool(_WARN_LINE.search(part)),
                    **base_meta,
                )
            )

    def _emit_step_groups(
        self,
        section: ParsedSection,
        path: list[str],
        base_meta: dict,
        text: str,
        chunks: list[Chunk],
        doc: ParsedDocument,
    ) -> None:
        lines = text.splitlines()
        intro_lines: list[str] = []
        steps: list[tuple[int, str]] = []
        for line in lines:
            if (m := _STEP_LINE.match(line)) :
                steps.append((int(m.group(1)), m.group(2).strip()))
            elif not steps:
                intro_lines.append(line)
            else:
                # trailing note after steps: attach to the last step's group text
                if steps:
                    num, txt = steps[-1]
                    steps[-1] = (num, f"{txt} {line.strip()}".strip())

        if len(intro_lines) >= 2 and "\n".join(intro_lines).strip():
            intro = "\n".join(intro_lines).strip()
            chunks.append(
                Chunk(
                    id=self._chunk_id(doc.source_doc, path, "sec"),
                    text=f"[{' > '.join(path)}]\n\n{intro}",
                    breadcrumb=list(path),
                    chunk_type="section",
                    code_anchors=_codes_in(intro),
                    safety=section.safety or bool(_WARN_LINE.search(intro)),
                    **base_meta,
                )
            )

        for g_start in range(0, len(steps), self.step_group_size):
            group = steps[g_start : g_start + self.step_group_size]
            lo, hi = group[0][0], group[-1][0]
            body = "\n".join(f"{num}. {txt}" for num, txt in group)
            group_path = [*path, f"Step {lo}-{hi}"]
            chunks.append(
                Chunk(
                    id=self._chunk_id(doc.source_doc, group_path, "steps"),
                    text=f"[{' > '.join(group_path)}]\n\n{body}",
                    breadcrumb=group_path,
                    chunk_type="steps",
                    code_anchors=_codes_in(body),
                    safety=section.safety or bool(_WARN_LINE.search(body)),
                    **base_meta,
                )
            )

    def _split_long(self, text: str) -> list[str]:
        """Split oversized section bodies into paragraph groups with 1-paragraph overlap."""
        if len(text) <= self.max_chunk_chars:
            return [text]
        paragraphs = [p for p in text.split("\n\n") if p.strip()]
        parts: list[str] = []
        buffer: list[str] = []
        size = 0
        for paragraph in paragraphs:
            plen = len(paragraph)
            if buffer and size + plen > self.max_chunk_chars:
                parts.append("\n\n".join(buffer))
                buffer = [buffer[-1], paragraph]  # overlap: carry last paragraph forward
                size = len(buffer[-2]) + plen
            else:
                buffer.append(paragraph)
                size += plen
        if buffer:
            parts.append("\n\n".join(buffer))
        return parts

    @staticmethod
    def _chunk_id(source_doc: str, path: list[str], kind: str, ordinal: int | None = None) -> str:
        stem = _slug(source_doc.rsplit(".", 1)[0])
        parts = [stem, *[(_slug(p) or "x") for p in path[1:]], kind]
        if ordinal:
            parts.append(f"p{ordinal}")
        return ":".join(parts)
