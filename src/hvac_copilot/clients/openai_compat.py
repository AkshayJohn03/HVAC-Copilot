"""OpenAI-compatible HTTP implementations of the provider protocols.

Any endpoint that speaks the ``/chat/completions`` and ``/embeddings`` shape
works (OpenAI, Azure-ish gateways, vLLM, LM Studio, Ollama's compat layer).

An optional ``transport`` (httpx) is accepted on every client so unit tests can
inject ``httpx.MockTransport`` and exercise request/response shaping without a
network. The production code path never touches the network unless a live
provider is explicitly configured.
"""

from __future__ import annotations

import base64
import json
import mimetypes
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from hvac_copilot.clients.base import Message

_DEFAULT_TIMEOUT = httpx.Timeout(60.0)


def _payload(messages: list[Message], model: str, temperature: float | None, max_tokens: int | None, stream: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "stream": stream,
    }
    if temperature is not None:
        body["temperature"] = temperature
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return body


class OpenAIBackendMixin:
    """Shared httpx plumbing for the OpenAI-compatible clients."""

    provider = "openai"

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=timeout,
        )
        self.model = model

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAILLMClient(OpenAIBackendMixin):
    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        response = await self._client.post(
            "/chat/completions",
            json=_payload(messages, self.model, temperature, max_tokens, stream=False),
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        request = self._client.build_request(
            "POST",
            "/chat/completions",
            json=_payload(messages, self.model, temperature, max_tokens, stream=True),
        )
        response = await self._client.send(request, stream=True)
        try:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[len("data:") :].strip()
                if chunk in ("", "[DONE]"):
                    if chunk == "[DONE]":
                        break
                    continue
                delta = json.loads(chunk)["choices"][0].get("delta", {})
                if piece := delta.get("content"):
                    yield piece
        finally:
            await response.aclose()


class OpenAIEmbeddingClient(OpenAIBackendMixin):
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "text-embedding-3-small",
        *,
        dim: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(api_key, base_url, model, transport=transport)
        self.dim = dim or 0  # resolved lazily on first embed if unset

    def embed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        return asyncio.run(self._embed(texts))

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        response = await self._client.post(
            "/embeddings", json={"model": self.model, "input": list(texts)}
        )
        response.raise_for_status()
        vectors = [item["embedding"] for item in response.json()["data"]]
        if not self.dim:
            self.dim = len(vectors[0])
        return vectors


class OpenAIVLMClient(OpenAIBackendMixin):
    async def describe(self, image_path: str | Path, prompt: str | None = None) -> str:
        path = Path(image_path)
        mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        data_uri = f"data:{mime};base64,{encoded}"
        text = prompt or (
            "Read this equipment nameplate. Report unit brand, model number and "
            "serial exactly as written. If the plate is unreadable, say "
            "'model plate unreadable'."
        )
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": text},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }
            ],
            "stream": False,
        }
        response = await self._client.post("/chat/completions", json=body)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
