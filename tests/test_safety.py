"""Safety escalation: retrieval-grounded refusal beats model refusal."""

from __future__ import annotations

import pytest

from hvac_copilot.safety_policy import detect_safety_topics


@pytest.mark.asyncio
async def test_escalation_fires_when_safety_sources_excluded(service):
    ans = await service.ask(
        "How do I recover refrigerant from the unit?", unit_model="X200", safety=False
    )
    assert ans.escalation is True
    assert "refrigerant" in ans.escalation_topics
    assert "certified" in ans.answer.lower()
    assert "supervisor" in ans.answer.lower()


@pytest.mark.asyncio
async def test_no_escalation_when_safety_section_present(service):
    """The X200/V9 safety chapters cover refrigerant recovery — with them in
    scope the assistant cites the manual instead of refusing."""
    ans = await service.ask("How do I safely recover refrigerant from the V9 chiller?")
    assert ans.escalation is False
    assert ans.citations, "grounded procedural answer must cite the safety section"
    assert any(c.safety for c in ans.citations), "at least one citation must be safety-tagged"


def test_topic_detection_two_tier_design():
    # work phrase -> escalates
    assert "refrigerant" in detect_safety_topics("recover the R32 charge")
    # designation alone is a spec lookup, not hazardous work
    assert detect_safety_topics("how much R32 charge does the unit carry") == []
    # diagnostic electrical lookup must not escalate; live work must
    assert detect_safety_topics("which terminal is the sensor connected to") == []
    assert "energized-electrical" in detect_safety_topics("discharge the capacitor first")
