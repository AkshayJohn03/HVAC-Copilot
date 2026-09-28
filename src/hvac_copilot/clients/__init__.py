"""Provider clients: protocols + OpenAI-compatible impls + offline mocks."""

from __future__ import annotations

from hvac_copilot.clients.base import EmbeddingClient, LLMClient, Message, VLMClient
from hvac_copilot.clients.mock import LocalHashEmbedding, MockLLMClient, MockVLMClient
from hvac_copilot.config import Settings

__all__ = [
    "EmbeddingClient",
    "LLMClient",
    "LocalHashEmbedding",
    "Message",
    "MockLLMClient",
    "MockVLMClient",
    "VLMClient",
    "build_clients",
]


def build_clients(settings: Settings) -> tuple[LLMClient, VLMClient, EmbeddingClient]:
    """Factory: wire the configured providers. Offline by default.

    Unknown provider names fail fast here rather than deep inside a request.
    """
    llm: LLMClient
    vlm: VLMClient
    embedder: EmbeddingClient

    if settings.llm_provider == "mock":
        llm = MockLLMClient()
    elif settings.llm_provider == "openai":
        from hvac_copilot.clients.openai_compat import OpenAILLMClient

        if not settings.llm_api_key:
            raise ValueError("HVAC_LLM_PROVIDER=openai requires HVAC_LLM_API_KEY")
        llm = OpenAILLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    else:
        raise ValueError(f"unknown llm_provider {settings.llm_provider!r}")

    if settings.vlm_provider == "mock":
        vlm = MockVLMClient()
    elif settings.vlm_provider == "openai":
        from hvac_copilot.clients.openai_compat import OpenAIVLMClient

        if not settings.vlm_api_key:
            raise ValueError("HVAC_VLM_PROVIDER=openai requires HVAC_VLM_API_KEY")
        vlm = OpenAIVLMClient(settings.vlm_api_key, settings.vlm_base_url, settings.vlm_model)
    else:
        raise ValueError(f"unknown vlm_provider {settings.vlm_provider!r}")

    if settings.embedding_provider == "local-hash":
        embedder = LocalHashEmbedding(dim=settings.embedding_dim)
    elif settings.embedding_provider == "openai":
        from hvac_copilot.clients.openai_compat import OpenAIEmbeddingClient

        if not settings.embedding_api_key:
            raise ValueError("HVAC_EMBEDDING_PROVIDER=openai requires HVAC_EMBEDDING_API_KEY")
        embedder = OpenAIEmbeddingClient(
            settings.embedding_api_key,
            settings.embedding_base_url,
            settings.embedding_model,
            dim=settings.embedding_dim,
        )
    else:
        raise ValueError(f"unknown embedding_provider {settings.embedding_provider!r}")

    return llm, vlm, embedder
