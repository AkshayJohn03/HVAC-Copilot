"""Markdown document parsing for HVAC service manuals.

Pipeline: raw markdown -> cleaned lines -> heading tree -> tables / images /
warning blocks registered per section.

Design notes:

- The parser is a single cursor-based scan (O(n)); tables are consumed inline
  so their lines never leak into section prose.
- Every fault-code table builds a *row registry* (``code -> {column: value}``)
  which powers the exact-match fast path downstream -- retrieval is not needed
  to answer "what is E04".
- Safety detection is dual: heading keywords mark whole sections, DANGER /
  WARNING lines mark their containing section. CAUTION/NOTICE are recorded but
  do not flip the safety flag (they are advisory, not safety-critical).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import IO

from pydantic import BaseModel, Field

# --- unit identification ------------------------------------------------------
UNIT_PATTERNS: dict[str, str] = {
    "X200": r"\bAriaTherm\s+X\s?-?200\b|\bX\s?-?200\b",
    "V9": r"\bVeyraCool\s+V\s?-?9\b|\bV\s?-?9\b",
}

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
_IMAGE = re.compile(r"!\[(.*?)\]\((.*?)\)")
_WARN_LINE = re.compile(
    r"^\s*>?\s*(?:⚠|‼|❗)?\s*(?:\*\*)?(DANGER|WARNING|CAUTION|NOTICE)(?:\*\*)?\s*[:!-]\s*(.*)",
    re.IGNORECASE,
)
_CODE_CELL = re.compile(r"\b([A-Z]{1,3}\s?-?\d{2,3})\b")
_SAFETY_HEADINGS = ("safety", "refrigerant", "loto", "lockout", "hazard", "danger")
_BOILERPLATE: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*(revision|rev\.?)\s+[\d.]+.*$", re.IGNORECASE),
    re.compile(r"^\s*©.*$"),
    re.compile(r"^\s*\*{3,}\s*$"),
    re.compile(r"^\s*-{5,}\s*$"),
)


def detect_unit_model(text: str) -> str | None:
    for unit, pattern in UNIT_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE):
            return unit
    return None


def _de_hyphenate(text: str) -> str:
    """Join words broken across lines: 'cool-\\ning' -> 'cooling'."""
    return re.sub(r"(\w)-\n(\w)", r"\1\2", text)


def strip_boilerplate(lines: list[str]) -> list[str]:
    """Drop running headers/footers (page numbers, revision stamps, rules)."""
    return [line for line in lines if not any(p.match(line) for p in _BOILERPLATE)]


class ParsedTable(BaseModel):
    table_id: str
    caption: str | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    raw_markdown: str = ""
    code_column: int | None = None
    row_codes: dict[int, list[str]] = Field(default_factory=dict)
    row_data: dict[str, dict[str, str]] = Field(default_factory=dict)

    @property
    def is_fault_table(self) -> bool:
        return bool(self.row_data)


class ImageRef(BaseModel):
    alt: str
    src: str
    caption: str | None = None


class ParsedSection(BaseModel):
    title: str
    level: int
    text: str = ""
    tables: list[ParsedTable] = Field(default_factory=list)
    images: list[ImageRef] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safety: bool = False
    children: list[ParsedSection] = Field(default_factory=list)

    def iter_self_and_children(self):
        yield self
        for child in self.children:
            yield from child.iter_self_and_children()


class ParsedDocument(BaseModel):
    source_doc: str
    title: str
    unit_model: str | None = None
    doc_type: str = "manual"
    sections: list[ParsedSection] = Field(default_factory=list)

    def iter_sections(self):
        for section in self.sections:
            yield from section.iter_self_and_children()


class TableExtractor:
    """Extracts markdown pipe tables; builds fault-code row registries."""

    def __init__(self, doc_prefix: str) -> None:
        self._counter = 0
        self._prefix = doc_prefix

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self._prefix}::table{self._counter}"

    @staticmethod
    def _split_row(line: str) -> list[str]:
        return [cell.strip() for cell in line.strip().strip("|").split("|")]

    @staticmethod
    def _find_code_column(headers: list[str]) -> int | None:
        for idx, header in enumerate(headers):
            if re.search(r"\bcode\b|fault", header, re.IGNORECASE):
                return idx
        return None

    def extract(self, lines: list[str], start: int) -> tuple[ParsedTable, int] | None:
        """Parse the table starting at ``lines[start]``; return (table, next_index)."""
        if start >= len(lines) or not _TABLE_ROW.match(lines[start]):
            return None
        block: list[str] = []
        i = start
        while i < len(lines) and _TABLE_ROW.match(lines[i]):
            block.append(lines[i].rstrip())
            i += 1
        if len(block) < 2:  # header + separator minimum
            return None

        headers = self._split_row(block[0])
        rows = [self._split_row(line) for line in block[1:] if not _TABLE_SEP.match(line)]

        code_col = self._find_code_column(headers)
        row_codes: dict[int, list[str]] = {}
        if code_col is not None:
            for r_idx, row in enumerate(rows):
                cell = row[code_col] if code_col < len(row) else ""
                found = [m.group(1).replace(" ", "") for m in _CODE_CELL.finditer(cell)]
                if found:
                    row_codes[r_idx] = found

        row_data: dict[str, dict[str, str]] = {}
        if code_col is not None:
            for r_idx, codes in row_codes.items():
                row = rows[r_idx]
                for code in codes:
                    row_data[code] = {
                        header: (row[c] if c < len(row) else "")
                        for c, header in enumerate(headers)
                    }

        # Caption: nearest previous non-empty line, matching the "Table: ..." convention.
        caption = None
        j = start - 1
        while j >= 0 and not lines[j].strip():
            j -= 1
        if j >= 0 and (m := re.match(r"^(?:\*\*)?\s*Table:\s*(.+?)(?:\*\*)?\s*$", lines[j], re.IGNORECASE)):
            caption = m.group(1).strip()

        table = ParsedTable(
            table_id=self._next_id(),
            caption=caption,
            headers=headers,
            rows=rows,
            raw_markdown="\n".join(block),
            code_column=code_col,
            row_codes=row_codes,
            row_data=row_data,
        )
        return table, i


def parse_markdown(text: str, source_doc: str) -> ParsedDocument:
    """Parse a manual chapter into a structured document tree."""
    lines = strip_boilerplate(_de_hyphenate(text).splitlines())

    title = source_doc
    unit: str | None = None
    sections: list[ParsedSection] = []
    stack: list[tuple[int, ParsedSection]] = []
    extractor = TableExtractor(source_doc)

    current: ParsedSection | None = None
    body: list[str] = []
    recent_lines: list[str] = []  # short rolling window for image captions

    def flush_body() -> None:
        if current is not None:
            current.text = "\n".join(body).strip()
        body.clear()

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if heading := _HEADING.match(line):
            flush_body()
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if level == 1 and not sections:
                title = heading_text
                unit = unit or detect_unit_model(heading_text)
                i += 1
                continue
            section = ParsedSection(title=heading_text, level=level)
            lowered = heading_text.lower()
            section.safety = any(word in lowered for word in _SAFETY_HEADINGS)
            unit = unit or detect_unit_model(heading_text)
            while stack and stack[-1][0] >= level:
                stack.pop()
            if stack:
                stack[-1][1].children.append(section)
            else:
                sections.append(section)
            stack.append((level, section))
            current = section
            i += 1
            continue

        if current is None:
            # Preamble before the first heading: treat as an implicit root section.
            current = ParsedSection(title="(introduction)", level=2)
            sections.append(current)
            stack.append((2, current))

        if _TABLE_ROW.match(line):
            result = extractor.extract(lines, i)
            if result is not None:
                table, consumed = result
                current.tables.append(table)
                i = consumed
                continue

        if image_match := _IMAGE.search(line):
            caption = None
            for candidate in reversed(recent_lines):
                if not _IMAGE.search(candidate) and len(candidate) > 12:
                    caption = candidate.strip()
                    break
            current.images.append(
                ImageRef(alt=image_match.group(1), src=image_match.group(2), caption=caption)
            )
            i += 1
            continue

        if warn_match := _WARN_LINE.match(line):
            kind = warn_match.group(1).upper()
            detail = warn_match.group(2).strip()
            current.warnings.append(f"{kind}: {detail}".rstrip())
            if kind in ("DANGER", "WARNING"):
                current.safety = True

        body.append(line)
        if line.strip():
            recent_lines.append(line.strip())
            if len(recent_lines) > 3:
                recent_lines.pop(0)
        i += 1

    flush_body()

    # Safety propagation: a safety-flagged section flags its descendants, and a
    # document whose title is a safety chapter flags every section in it.
    title_is_safety = any(word in title.lower() for word in _SAFETY_HEADINGS)

    def _propagate(section: ParsedSection, inherited: bool) -> None:
        section.safety = section.safety or inherited or title_is_safety
        for child in section.children:
            _propagate(child, section.safety)

    for root in sections:
        _propagate(root, False)

    return ParsedDocument(source_doc=source_doc, title=title, unit_model=unit, sections=sections)


def parse_markdown_file(fileobj: IO[str] | Path, source_doc: str | None = None) -> ParsedDocument:
    """Convenience wrapper for files / file handles."""
    if isinstance(fileobj, Path):
        text = fileobj.read_text(encoding="utf-8")
        return parse_markdown(text, source_doc or fileobj.name)
    text = fileobj.read()
    return parse_markdown(text, source_doc or "inline.md")
