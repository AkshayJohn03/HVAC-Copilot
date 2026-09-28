"""Query understanding: fault-code fast path, unit detection, slang normalisation.

Field technicians type fragments, not queries: "v9 keeps tripping", "what's
E04", "coil is icing up". This module turns that into a structured plan:

1. **Fault codes**: regex candidates validated against the indexed fault-code
   registry -> *direct hits* that skip fuzzy retrieval entirely. Safety property:
   the answer for "what is E04" is the exact table row, not a neighbourhood.
2. **Unit models**: X200 / V9 mentions (or class nouns like "heat pump"/"chiller")
   become metadata filters.
3. **Slang**: an offline normalisation table maps field phrasing to manual
   vocabulary; expansions are appended to the retrieval query (never shown to
   the user).
4. Optional LLM rephrasing is behind the LLMClient protocol and only runs when
   a live provider is configured; the offline path never blocks on it.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from hvac_copilot.ingest.indexer import IndexedSnapshot
from hvac_copilot.models import DirectHit
from hvac_copilot.safety_policy import detect_safety_topics

# Fault-code candidate: optional single letter prefix + 2-3 digits.
# Candidates are *validated* against the registry, so over-matching here is
# cheap; refrigerant designations and unit models are excluded explicitly.
_CODE_CANDIDATE = re.compile(r"\b([A-Z])\s?-?(\d{2,3})\b")
_REFRIGERANT_PREFIX = "R"
_UNIT_TOKENS = {"X200", "V9"}

_UNIT_EXPLICIT = {"X200": re.compile(r"\bX\s?-?200\b", re.IGNORECASE), "V9": re.compile(r"\bV\s?-?9\b", re.IGNORECASE)}
_UNIT_CLASS_NOUNS = {"X200": ("heat pump",), "V9": ("chiller",)}

# Field slang -> manual vocabulary. Keys are substrings matched case-insensitively.
SLANG_TABLE: dict[str, tuple[str, ...]] = {
    "not cooling": ("cooling capacity", "low capacity", "evaporator", "superheat"),
    "no cooling": ("cooling capacity", "low capacity", "evaporator", "superheat"),
    "not heating": ("heating capacity", "low capacity", "flow temperature"),
    "no heat": ("heating capacity", "low capacity"),
    "warm air": ("low capacity", "air temperature"),
    "icing": ("coil frost", "icing", "defrost", "evaporator"),
    "iced up": ("coil frost", "icing", "defrost"),
    "icing up": ("coil frost", "icing", "defrost"),
    "freezing up": ("coil frost", "icing", "defrost"),
    "frost on": ("coil frost", "defrost"),
    "tripping": ("breaker", "overcurrent", "trip", "electrical"),
    "trips": ("trip", "overcurrent", "breaker"),
    "keeps cutting out": ("trip", "lockout", "fault code"),
    "leaking water": ("condensate", "drain", "tray", "leak"),
    "water under": ("condensate", "tray", "drain", "overflow"),
    "water pooling": ("condensate", "tray", "drain", "overflow"),
    "dripping": ("condensate", "drain", "tray"),
    "noisy": ("noise", "vibration", "fan", "bearing"),
    "rattling": ("noise", "vibration", "fan", "debris"),
    "humming": ("noise", "inverter", "compressor"),
    "won't start": ("no power", "start", "contactor", "controller"),
    "wont start": ("no power", "start", "contactor"),
    "not starting": ("no power", "start", "contactor"),
    "no display": ("no power", "display", "supply"),
    "smells": ("burning odor", "electrical", "overheat"),
    "burning smell": ("burning odor", "electrical", "overheat"),
    "how much": ("factory charge", "charge weight"),
    "how many": ("factory charge", "charge weight"),
    "how do i": ("step", "procedure"),
    "how do you": ("step", "procedure"),
    "how to": ("step", "procedure"),
    "what size": ("specifications", "nominal"),
}

# Generic synonym expansions applied on every query (offline multi-query expansion).
SYNONYM_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "capacity": ("capacity", "output", "delta-t", "specifications", "nominal"),
    "wire": ("wiring", "conductor", "terminal", "cable"),
    "gauge": ("conductor", "cross-section", "mm²"),
    "part": ("spare", "order", "part number", "bom"),
    "fix": ("corrective action", "repair"),
    "reset": ("clear", "reset", "lockout"),
    "error": ("fault code",),
    "alarm": ("fault code",),
    "code": ("fault code",),
    "clean": ("cleaning", "rinse", "coil cleaning"),
    "flush": ("flush", "condensate tray", "drain"),
    "rated": ("nominal", "specifications"),
    "torque": ("torque", "nm"),
    "braze": ("brazing", "nitrogen purge", "torch", "joint"),
    "weld": ("brazing", "open flame"),
}

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("parts", ("part number", "part", "spare", "order ", "bom", "kit")),
    ("wiring", ("wire", "wiring", "terminal", "gauge", "mm²", "torque", "modbus", "rs-485", "conductor")),
    ("procedure", ("how do i", "how to", "steps", "procedure", "clean", "replace", "check", "verify", "flush", "top up")),
    ("specs", ("specification", "rated", "charge weight", "capacity of", "what size")),
]

_QUERY_CODE = re.compile(r"\bE\s?(\d{2,3})\b", re.IGNORECASE)


class QueryUnderstanding(BaseModel):
    raw_query: str
    retrieval_query: str
    expansions: list[str] = Field(default_factory=list)
    code_candidates: list[str] = Field(default_factory=list)
    codes: list[str] = Field(default_factory=list)  # validated against the registry
    unit_model: str | None = None
    safety_topics: list[str] = Field(default_factory=list)
    intent: str = "general"
    direct_hits: list[DirectHit] = Field(default_factory=list)


class QueryAnalyzer:
    """Stateful only through the (rebuildable) fault-code registry of the index."""

    def __init__(self, snapshot: IndexedSnapshot | None = None) -> None:
        self.set_snapshot(snapshot)

    def set_snapshot(self, snapshot: IndexedSnapshot | None) -> None:
        self.snapshot = snapshot

    # -- pieces -------------------------------------------------------------
    def _detect_unit(self, query: str) -> str | None:
        for unit, pattern in _UNIT_EXPLICIT.items():
            if pattern.search(query):
                return unit
        lowered = query.lower()
        for unit, nouns in _UNIT_CLASS_NOUNS.items():
            if any(noun in lowered for noun in nouns):
                return unit
        return None

    @staticmethod
    def _code_candidates(query: str) -> list[str]:
        candidates: list[str] = []
        for letter, digits in _CODE_CANDIDATE.findall(query.upper()):
            token = f"{letter}{digits}"
            if letter == _REFRIGERANT_PREFIX or token in _UNIT_TOKENS:
                continue  # R32, X200, ... are designations, not fault codes
            candidates.append(token)
        # Also catch bare "E04" style with optional lowercase (regex covers it).
        for digits in _QUERY_CODE.findall(query.upper()):
            token = f"E{digits}"
            if token not in candidates:
                candidates.append(token)
        return candidates

    @staticmethod
    def _expand(query: str) -> tuple[str, list[str]]:
        lowered = query.lower()
        expansions: list[str] = []
        for slang, terms in SLANG_TABLE.items():
            if slang in lowered:
                expansions.extend(terms)
        for word, terms in SYNONYM_EXPANSIONS.items():
            if re.search(rf"\b{re.escape(word)}\b", lowered):
                expansions.extend(t for t in terms if t not in expansions)
        # de-duplicate, keep order
        seen: set[str] = set()
        unique = [t for t in expansions if not (t in seen or seen.add(t))]
        retrieval_query = query if not unique else f"{query} {' '.join(unique)}"
        return retrieval_query, unique

    @staticmethod
    def _intent(query: str, codes: list[str]) -> str:
        if codes:
            return "fault_lookup"
        lowered = query.lower()
        for intent, keywords in _INTENT_RULES:
            if any(k in lowered for k in keywords):
                return intent
        return "general"

    def _direct_hits(self, codes: list[str], unit: str | None) -> list[DirectHit]:
        hits: list[DirectHit] = []
        if self.snapshot is None:
            return hits
        for code in codes:
            for chunk in self.snapshot.code_lookup(code):
                if unit and chunk.unit_model and chunk.unit_model != unit:
                    continue
                row = chunk.row_registry.get(code)
                if not row:
                    continue
                rendered = ", ".join(f"{key}: {value}" for key, value in row.items() if value)
                hits.append(
                    DirectHit(
                        code=code,
                        unit_model=chunk.unit_model,
                        chunk_ids=[chunk.id],
                        rendered_row=rendered,
                        row_data=dict(row),
                    )
                )
                break  # one authoritative row per code
        return hits

    # -- main ---------------------------------------------------------------
    def analyze(self, query: str, context_unit: str | None = None) -> QueryUnderstanding:
        retrieval_query, expansions = self._expand(query)
        candidates = self._code_candidates(query)
        registry = set(self.snapshot.fault_codes) if self.snapshot else set()
        codes = [c for c in candidates if c in registry]
        unit = self._detect_unit(query) or context_unit
        return QueryUnderstanding(
            raw_query=query,
            retrieval_query=retrieval_query,
            expansions=expansions,
            code_candidates=candidates,
            codes=codes,
            unit_model=unit,
            safety_topics=detect_safety_topics(query),
            intent=self._intent(query, codes),
            direct_hits=self._direct_hits(codes, unit),
        )
