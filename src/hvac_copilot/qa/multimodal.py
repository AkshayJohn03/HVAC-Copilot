"""Multimodal intake: technician photo -> unit identification -> targeted retrieval.

Field flow: the technician photographs the nameplate instead of typing a model
number. The VLM protocol reads the photo; when the model comes back, the query
is answered with the unit filter locked on. When the plate is unreadable
(the common offline case with the mock), the assistant asks for the model
number as text instead of guessing — a wrong unit guess on a refrigerant
charge question is worse than no answer.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from hvac_copilot.clients.base import VLMClient
from hvac_copilot.qa.compose import Answer
from hvac_copilot.retrieve.hybrid import Filters, HybridRetriever
from hvac_copilot.retrieve.understand import QueryAnalyzer

_UNREADABLE_MARKERS = ("unreadable", "cannot be read", "can't be read", "blur")


class PhotoQueryResult(BaseModel):
    status: str  # identified | unreadable
    description: str
    unit_model: str | None = None
    message: str = ""
    answer: Answer | None = None
    trace: dict = Field(default_factory=dict)


class MultimodalQuery:
    def __init__(self, vlm: VLMClient, composer, retriever: HybridRetriever, analyzer: QueryAnalyzer) -> None:
        self.vlm = vlm
        self.composer = composer
        self.retriever = retriever
        self.analyzer = analyzer

    @staticmethod
    def _unit_from_description(description: str) -> str | None:
        lowered = description.lower()
        if "x200" in lowered or "ariatherm" in lowered:
            return "X200"
        if "v9" in lowered or "veyracool" in lowered:
            return "V9"
        return None

    async def handle_photo(
        self,
        image_path: str | Path,
        question: str | None = None,
    ) -> PhotoQueryResult:
        description = await self.vlm.describe(image_path)

        if any(marker in description.lower() for marker in _UNREADABLE_MARKERS):
            return PhotoQueryResult(
                status="unreadable",
                description=description,
                message=(
                    "I couldn't read the model plate in that photo. Please type the "
                    "unit model number as text (e.g. X200 or V9) and ask again."
                ),
                trace={"vlm": "unreadable"},
            )

        unit = self._unit_from_description(description)
        if unit is None:
            return PhotoQueryResult(
                status="unreadable",
                description=description,
                message=(
                    "The photo was read but no known unit model was recognised. "
                    "Please type the model number (e.g. X200 or V9)."
                ),
                trace={"vlm": "no-unit"},
            )

        question = question or "Unit identification and key specifications"
        understanding = self.analyzer.analyze(f"{question} {description}", context_unit=unit)
        retrieved = self.retriever.search(
            understanding.retrieval_query or description,
            filters=Filters(unit_model=unit),
            top_k=5,
        )
        answer = await self.composer.answer(question, understanding, retrieved)
        answer.trace["vlm"] = "identified"
        return PhotoQueryResult(
            status="identified",
            description=description,
            unit_model=unit,
            answer=answer,
            trace=answer.trace,
        )
