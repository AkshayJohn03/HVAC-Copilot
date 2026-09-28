"""Deterministic offline mocks for every provider protocol.

These are not "dumb stubs":

- ``MockLLMClient`` is extractive — it reads the grounding context from the
  prompt and quotes it, so groundedness/citation metrics measure the real
  pipeline rather than an echo chamber.
- ``LocalHashEmbedding`` is a char-n-gram hashed bag-of-features vector.
  Documented as dev/test-grade: deterministic, dependency-free, no network,
  but NOT semantically comparable to a trained encoder. Its practical strength
  is robustness to typos and inflections (substring overlap at character level).
- ``MockVLMClient`` fakes nameplate reading via a filename/bytes heuristic so
  both multimodal outcomes (identified / unreadable) are testable offline.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re
from collections.abc import AsyncIterator
from pathlib import Path

from hvac_copilot.clients.base import Message

_CONTENT_BLOCK = re.compile(
    r"\[(?:C(\d+)|EXACT MATCH ([^\]]+))\][^\n]*\n(.*?)(?=\n\[(?:C\d+|EXACT MATCH)|\Z)",
    re.DOTALL,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by can do does for from has have how i in is it its "
    "me my not of on or that the this to up was we what when where which who why "
    "will with you your while still should do".split()
)


def _content_words(text: str) -> set[str]:
    return {t for t in _WORD.findall(text.lower()) if len(t) > 2 and t not in _STOPWORDS}


class MockLLMClient:
    """Extractive 'LLM': answers strictly by quoting the best-matching context blocks.

    Contract with the composer's prompt format: the user message contains
    ``QUESTION:`` and ``[Ci] <breadcrumb>\\n<text>`` context blocks.
    """

    provider = "mock"

    async def complete(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        user = messages[-1].content if messages else ""
        return _compose_extractive(user)

    async def stream(
        self,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        text = _compose_extractive(messages[-1].content if messages else "")
        for token in re.findall(r"\S+\s*", text):
            yield token


def _compose_extractive(prompt: str) -> str:
    question_match = re.search(r"QUESTION:\s*(.+)", prompt)
    question = question_match.group(1) if question_match else prompt
    q_words = _content_words(question)

    exact_blocks: list[str] = []
    scored: list[tuple[float, str]] = []
    block_index = 0
    for match in _CONTENT_BLOCK.finditer(prompt):
        kind = match.group(1)  # C-number, or None for EXACT MATCH blocks
        body = match.group(3).strip()
        if kind is None:  # exact fault-table row: authoritative, quoted verbatim
            exact_blocks.append(body)
            continue
        words = _content_words(body)
        if not words:
            continue
        overlap = len(q_words & words) / max(len(q_words), 1)
        # Length-normalised, with a mild rank prior: blocks appear in retrieval
        # rank order, so near-ties break toward the retriever's top choice.
        score = overlap / max(len(words) ** 0.5, 1.0) - 0.02 * block_index
        scored.append((score, body))
        block_index += 1

    lines: list[str] = []
    for body in exact_blocks[:2]:
        lines.append(f"- {body}")

    # The mock trusts the retriever: quote the highest-ranked block that has
    # any lexical tie to the question. Near-tie re-ranking by score invites
    # second-guessing a ranking that is usually right.
    best: tuple[float, str] | None = None
    for score, body in scored:
        overlap = len(q_words & _content_words(body)) / max(len(q_words), 1)
        if overlap > 0:
            best = (score, body)
            break
    if best is None and scored:
        best = max(scored, key=lambda pair: pair[0])

    if best is not None:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(best[1].replace("\n", " ")) if s.strip()]
        ranked = sorted(
            sentences,
            key=lambda s: len(q_words & _content_words(s)),
            reverse=True,
        )
        keep = [s for s in ranked[:2] if len(q_words & _content_words(s)) > 0]
        if not keep and sentences:
            keep = sentences[:1]
        for sentence in keep:
            lines.append(f"- {sentence}")

    if not lines:
        return (
            "The indexed documentation does not cover this question. "
            "Please consult the full service manual or contact technical support."
        )
    header = "Based on the service documentation:"
    return header + "\n" + "\n".join(lines)


class LocalHashEmbedding:
    """Deterministic hashed char-n-gram embedder (dev/test-grade).

    Features: per-word char n-grams (3..5) wrapped in boundary markers plus the
    whole word itself. Hashed with blake2b into a fixed-dim signed bag (sign
    trick halves collision bias), then L2 normalised. Fully deterministic
    across processes and platforms.

    ``fit(texts)`` upgrades the bag to hashed *TF-IDF*: sublinear term
    frequency times a smoothed inverse document frequency learned from the
    corpus (exactly the TfidfVectorizer recipe, minus vocabulary — the hashing
    trick needs no feature table). IDF weighting is what makes cosine
    discriminative on manual text: rare n-grams ("e23", "concentrat") dominate
    the direction, boilerplate n-grams ("ing", "the ") vanish. Without a fit
    the embedder still works, just noisier. Unseen query features are dropped
    (they carry no corpus evidence); typo bridging survives because the *seen*
    n-grams of a misspelling still match.

    Documented as dev/test-grade: lexical fuzz (typos, inflections), not
    semantics. Swap in a trained encoder behind the same protocol for real
    semantic matching.
    """

    provider = "local-hash"

    def __init__(self, dim: int = 384, ngram_range: tuple[int, int] = (3, 5)) -> None:
        if dim < 64:
            raise ValueError("embedding dim must be >= 64")
        self.dim = dim
        self.ngram_range = ngram_range
        self._df: dict[str, int] = {}
        self._n_docs = 0
        self.fit_digest = ""

    def fit(self, texts: list[str]) -> None:
        """Learn feature document frequencies from the corpus (idempotent)."""
        import hashlib as _hashlib

        df: dict[str, int] = {}
        for text in texts:
            for feature in set(self._features(text)):
                df[feature] = df.get(feature, 0) + 1
        self._df = df
        self._n_docs = len(texts)
        # Digest of the fit state: snapshots re-embed when the corpus (and
        # therefore the IDF table) changes.
        material = "\n".join(sorted(f"{k}:{v}" for k, v in df.items()))
        self.fit_digest = _hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]

    def _weight(self, feature: str, tf: int) -> float:
        base = 1.0 + math.log(tf)  # sublinear TF
        if self._n_docs:
            df = self._df.get(feature)
            if df is None:
                return 0.0  # unseen in corpus: no evidence, dropped
            idf = math.log((self._n_docs + 1) / (df + 1)) + 1.0
            return base * idf
        return base

    def _hash(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def _features(self, text: str) -> list[str]:
        words = _WORD.findall(text.lower())
        feats: list[str] = []
        for word in words:
            feats.append(f"w:{word}")
            wrapped = f"↑{word}↓"
            for n in range(self.ngram_range[0], self.ngram_range[1] + 1):
                if len(wrapped) < n:
                    continue
                feats.extend(f"g:{wrapped[i : i + n]}" for i in range(len(wrapped) - n + 1))
        return feats

    def embed_one(self, text: str) -> list[float]:
        counts: dict[str, int] = {}
        for feature in self._features(text):
            counts[feature] = counts.get(feature, 0) + 1
        vec = [0.0] * self.dim
        for feature, tf in counts.items():
            weight = self._weight(feature, tf)
            if weight == 0.0:
                continue
            idx, sign = self._hash(feature)
            vec[idx] += sign * weight
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(t) for t in texts]


class MockVLMClient:
    """Offline VLM stand-in.

    Heuristic: if the image "file" name or bytes hint at a unit model, pretend
    the nameplate was read successfully; otherwise report the plate as
    unreadable. This keeps both multimodal code paths exercisable offline.
    """

    provider = "mock"

    async def describe(self, image_path: str | Path, prompt: str | None = None) -> str:
        path = Path(image_path)
        name = path.name.lower()
        try:
            blob = path.read_bytes()[:4096].decode("utf-8", errors="ignore").lower()
        except OSError:
            blob = ""
        if "x200" in name or "x200" in blob:
            return (
                "Metal nameplate read successfully: unit AriaTherm X200 air-to-water "
                "heat pump, model X200-16, serial ATX200-0042, refrigerant R32, "
                "rated 230V 50Hz."
            )
        if "v9" in name or "v9" in blob:
            return (
                "Metal nameplate read successfully: unit VeyraCool V9 air-cooled "
                "chiller, model V9-140, serial VYC9-1187, refrigerant R513A, "
                "rated 400V 3ph 50Hz."
            )
        return (
            "model plate unreadable: the nameplate photo is blurred and the model "
            "number cannot be read"
        )


def fake_image_bytes(hint: str = "") -> bytes:
    """Tiny helper for tests/fixtures: a fake 'photo' carrying a model hint."""
    return base64.b64encode(f"PHOTO:{hint}".encode())
