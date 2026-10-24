"""Embedding abstraction.

Two implementations behind one interface:
- OpenAIEmbeddingProvider — real embeddings via the OpenAI API (used when
  OPENAI_API_KEY is set; model configurable).
- LocalHashEmbeddingProvider — deterministic hashed bag-of-words vectors.
  No semantic power, but exact-term retrieval works, tests and keyless demos
  run offline, and the interface is identical. Clearly not "smart" RAG —
  swap in the real provider by setting a key.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from pydantic import SecretStr

_WORD = re.compile(r"[a-z0-9а-яё]+", re.IGNORECASE)
LOCAL_DIM = 512

# Very common words carry no signal and make unrelated texts look similar.
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its may of on or
    that the their this to was were will with во и не на по из за от до для""".split()
)


class EmbeddingProvider(Protocol):
    name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    def __init__(self, api_key: str, model: str = "text-embedding-3-small") -> None:
        from langchain_openai import OpenAIEmbeddings

        self.name = f"openai:{model}"
        self._client = OpenAIEmbeddings(model=model, api_key=SecretStr(api_key))

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._client.aembed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        return await self._client.aembed_query(text)


class LocalHashEmbeddingProvider:
    """Deterministic token-hash embeddings (exact-term matching).

    Documents and queries sharing distinctive terms land near each other;
    unrelated text does not (stopwords filtered). This is keyword retrieval
    wearing an embedding interface — deliberately simple and offline. Real
    semantic retrieval comes from the OpenAI provider behind the same
    interface.
    """

    name = "local-hash"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * LOCAL_DIM
        tokens = [t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS]
        for token in tokens:
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % LOCAL_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[index] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def build_embedding_provider(settings) -> EmbeddingProvider:
    if settings.openai_api_key:
        return OpenAIEmbeddingProvider(settings.openai_api_key)
    return LocalHashEmbeddingProvider()
