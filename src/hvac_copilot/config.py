"""Typed application settings (pydantic-settings).

Defaults are fully offline: ``mock`` LLM/VLM providers and the deterministic
``local-hash`` embedder. Point the providers at an OpenAI-compatible endpoint
via environment variables (see ``.env.example``) to upgrade to live models.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]

RERANKER_CHOICES = ("bm25", "cross-encoder", "none")


def _default_corpus_dir() -> Path:
    """Resolve the bundled corpus: prefer cwd, fall back to the repo checkout."""
    cwd_candidate = Path.cwd() / "corpus"
    if cwd_candidate.exists():
        return cwd_candidate
    return REPO_ROOT / "corpus"


class Settings(BaseSettings):
    """All runtime knobs. Every field maps to an ``HVAC_*`` environment variable."""

    model_config = SettingsConfigDict(
        env_prefix="HVAC_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "hvac-copilot"

    # --- LLM ---
    llm_provider: str = "mock"  # mock | openai
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1

    # --- VLM (nameplate / photo reading) ---
    vlm_provider: str = "mock"  # mock | openai
    vlm_api_key: str | None = None
    vlm_base_url: str = "https://api.openai.com/v1"
    vlm_model: str = "gpt-4o-mini"

    # --- Embeddings ---
    embedding_provider: str = "local-hash"  # local-hash | openai
    embedding_api_key: str | None = None
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 384  # used by the local hash embedder

    # --- Paths ---
    corpus_dir: Path = Field(default_factory=_default_corpus_dir)
    index_dir: Path = Field(default_factory=lambda: REPO_ROOT / ".index")
    golden_path: Path = Field(default_factory=lambda: REPO_ROOT / "data" / "qa_golden.jsonl")

    # --- Retrieval ---
    top_k: int = 5
    pool_size: int = 50
    bm25_k1: float = 1.5
    bm25_b: float = 0.75
    rrf_k: int = 60  # standard RRF constant; see README "Design decisions"
    reranker: str = "bm25"  # bm25 | cross-encoder | none
    mmr_lambda: float = 0.0  # 0 disables MMR

    # --- Composition / guardrail ---
    guardrail_enabled: bool = True
    max_citations: int = 2

    # --- Latency pack ---
    query_cache_size: int = 256
    semantic_cache_threshold: float = 0.93

    @field_validator("reranker")
    @classmethod
    def _check_reranker(cls, value: str) -> str:
        if value not in RERANKER_CHOICES:
            raise ValueError(f"reranker must be one of {RERANKER_CHOICES}, got {value!r}")
        return value

    def ensure_dirs(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
