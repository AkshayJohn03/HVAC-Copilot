"""Safety policy: topic detection + escalation copy.

Centralising the guardrail here means query understanding (``retrieve``), answer
composition (``qa``) and evaluation (``eval``) all agree on what counts as
safety-critical. Categories and thresholds are documented in the README under
"Design decisions" -> "Safety escalation".
"""

from __future__ import annotations

import re

# Topic -> keyword stems. Matching is substring on lowercased text; stems are
# chosen to catch inflections (braze/brazing/brazed, pressurise/pressurized).
#
# Two tiers, because escalation on informational lookups trains users to ignore
# the guardrail:
#   - ALWAYS: the phrase itself describes hazardous work or a hazard state.
#   - DESIGNATION: a refrigerant/gas name only counts as a safety topic when the
#     text also contains a work verb ("recover R32" escalates; "how much R32
#     charge does the unit carry" is a spec lookup and must not).
SAFETY_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    # Refrigerant handling: open flame on circuits, recovery, A2L precautions.
    # Phrases here describe hazardous work itself. Descriptive nouns like
    # "refrigerant circuit" are NOT triggers on their own (they appear in
    # schedules, parts notes, troubleshooting trees); they fire through the
    # designation+work-verb path below instead. "top up"/"refill" are work
    # verbs, not triggers: "top up the glycol" is routine, "top up the R513A"
    # is not.
    "refrigerant": (
        "braz", "solder", "nitrogen purge", "recover", "recovery", "recharge",
        "evacuate", "evacuation", "leak seal",
        "charging the system", "charge the system", "open the circuit",
        "refrigerant work", "refrigerant handling",
    ),
    # Pressurised circuits: anything that can rupture or spray. Targeted
    # phrases on purpose: a bare "pressur" stem would fire on benign water-loop
    # text like "re-pressurise to 1.0-1.5 bar", and a guardrail that fires on
    # condensate flushing trains users to ignore it.
    "pressurized": (
        "pressurised system", "pressurized system", "pressure test", "pressure decay",
        "relief valve", "burst disc", "bursting disc", "schrader", "overpressure",
        "pressurise the refrigerant", "pressurize the refrigerant",
    ),
    # Energised electrical work only. Diagnostic lookups ("what gauge wire",
    # "which terminal is the sensor") are informational and must NOT escalate;
    # hands-on work on live equipment must.
    "energized-electrical": (
        "live wire", "live circuit", "mains", "energiz", "energis", "loto",
        "lock out", "lockout", "lock-out", "capacitor", "discharge the", "busbar",
        "bus bar", "insulation resistance", "megger", "earth fault", "ground fault",
        "electrocut", "hot work", "panel live",
    ),
    # Gas/combustion (future-proofing for gas-fired units in the same fleet).
    "gas": ("gas leak", "combustion", "burner gas", "gas valve", "carbon monoxide"),
}

# Refrigerant/gas designations: safety topics ONLY in combination with a work verb.
SAFETY_DESIGNATIONS: tuple[str, ...] = (
    "r32", "r-32", "r410", "r-410", "r134a", "r-134a", "r513a", "r-513a",
    "refrigerant",
)

# Work verbs that turn a designation into hazardous work.
SAFETY_WORK_VERBS: tuple[str, ...] = (
    "braz", "solder", "weld", "grind", "recover", "repair", "replace", "evacuate",
    "top up", "top-up", "recharge", "refill", "purge", "open", "vent", "drain",
    "disconnect", "charge ", "charging", "test", "weigh in",
)

_NUM_STEPS = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
# "how much R32 charge does the unit carry" is a SPEC LOOKUP, not work: a
# quantity question about a designation never escalates, no matter which work
# verbs appear elsewhere in the sentence.
_SPEC_LOOKUP = re.compile(
    r"\bhow\s+(much|many|long)[^.;]{0,60}\b(r[- ]?\d+\w*|refrigerant|gas)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(r"\b(not|never|no |cannot|can't|don't|do not|unsafe|prohibited)\b", re.IGNORECASE)


def detect_safety_topics(text: str) -> list[str]:
    """Return the safety categories mentioned in ``text`` (query or document text)."""
    lowered = text.lower()
    topics: list[str] = []
    for topic, keywords in SAFETY_TOPIC_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            topics.append(topic)
    has_work_verb = any(verb in lowered for verb in SAFETY_WORK_VERBS)
    if has_work_verb and any(designation in lowered for designation in SAFETY_DESIGNATIONS) and not _SPEC_LOOKUP.search(lowered):
        if "refrigerant" not in topics:
            topics.append("refrigerant")
    return sorted(set(topics))


def is_safety_relevant(text: str) -> bool:
    return bool(detect_safety_topics(text))


def is_procedural(text: str) -> bool:
    """Heuristic: does the text look like a step-by-step work instruction?"""
    return len(_NUM_STEPS.findall(text)) >= 3


def escalation_message(topics: list[str], nearest_section: str | None, unit_model: str | None) -> str:
    """The grounded-refusal copy. Always names the topic categories, always
    points at the nearest safety section, always escalates to a human."""
    topic_txt = ", ".join(sorted(topics)) if topics else "safety-critical work"
    unit_txt = f" for the {unit_model}" if unit_model else ""
    section_txt = (
        f" The nearest safety documentation is \"{nearest_section}\"{unit_txt and ' in the ' + unit_model + ' manual'}."
        if nearest_section
        else " No matching safety section is currently indexed for this unit."
    )
    return (
        "I can't give procedural guidance for this. The question involves "
        f"{topic_txt}{unit_txt}, which is safety-critical, and no section tagged as "
        "safety documentation supports an answer here. "
        "Stop and contact a certified HVAC technician; a supervisor has been flagged "
        "to review this request." + section_txt
    )
