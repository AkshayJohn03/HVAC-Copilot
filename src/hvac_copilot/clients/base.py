"""Provider protocols: LLM, VLM and embeddings.

Every consumer in the pipeline depends on these protocols, never on concrete
SDKs. Two implementations ship for each: OpenAI-compatible HTTP clients (for
real endpoints) and deterministic offline mocks (for tests and field-offline
demo mode).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class Message(BaseModel):
    role: str
    content: str


@runtime_checkable
class LLMClient(Protocol):
    """Text completion backend."""

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Return the full completion text."""
        ...

    def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Yield completion text incrementally."""
        ...


@runtime_checkable
class VLMClient(Protocol):
    """Vision backend: image -> textual description (e.g. a nameplate read)."""

    async def describe(self, image_path: str | Path, prompt: str | None = None) -> str: ...


@runtime_checkable
class EmbeddingClient(Protocol):
    """Dense embedding backend."""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts into L2-normalisable float vectors."""
        ...
