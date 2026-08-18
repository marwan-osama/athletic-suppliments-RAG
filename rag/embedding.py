"""Stage 4 — text to vectors, via the local model server."""

from __future__ import annotations

import hashlib
import math
from typing import List, Sequence

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from .llm import LLMClient
from .utils import batched


class ServerEmbedder(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by an OpenAI-shaped server.

    Retrieval embedders are asymmetric — they are trained with one instruction on
    the query side and another on the document side — and the `/embeddings`
    endpoint has no field for that, so the instruction is prepended here.
    `__call__` embeds documents, `embed_query` embeds searches.

    EmbeddingGemma's own templates are the defaults (see `config.py`), and they
    earn their place: on a creatine query against a matching and a mismatched
    passage they separated the two by 0.47, against 0.35 with no prefixes at all.
    Set both to "" for a symmetric model.
    """

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "embeddinggemma",
        batch_size: int = 16,
        document_prefix: str = "",
        query_prefix: str = "",
        dimensions: int = 768,
    ):
        self.client = client
        self.model_name = model_name
        self.batch_size = batch_size
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix
        self._dimensions = dimensions

    @staticmethod
    def name() -> str:
        # Lets Chroma persist/identify the EF config without warnings.
        return "server_embedding_fn"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def __call__(self, input: Documents) -> Embeddings:
        return self.embed(list(input), self.document_prefix)

    def embed_query(self, query: str) -> List[float]:
        return self.embed([query], self.query_prefix)[0]

    def embed(self, texts: Sequence[str], prefix: str = "") -> List[List[float]]:
        vectors: List[List[float]] = []
        for batch in batched(list(texts), self.batch_size):
            payload = [f"{prefix}{text}" for text in batch]
            vectors.extend(
                _normalize(vector)
                for vector in self.client.embed(self.model_name, payload)
            )
        return vectors


class HashEmbedder(EmbeddingFunction):
    """Offline stand-in: deterministic bag-of-words vectors, no server needed.

    Retrieval quality is poor (it only matches shared words), but it makes the UI
    and the tests runnable with nothing running.
    """

    def __init__(self, output_dim: int = 256):
        self.output_dim = output_dim

    @staticmethod
    def name() -> str:
        return "hash_embedding_fn"

    @property
    def dimensions(self) -> int:
        return self.output_dim

    def __call__(self, input: Documents) -> Embeddings:
        return [self._vector(text) for text in input]

    def embed_query(self, query: str) -> List[float]:
        return self._vector(query)

    def _vector(self, text: str) -> List[float]:
        vector = [0.0] * self.output_dim
        for word in text.lower().split():
            token = "".join(ch for ch in word if ch.isalnum())
            if token:
                digest = hashlib.md5(token.encode("utf-8")).digest()
                vector[digest[0] % self.output_dim] += 1.0
        return _normalize(vector)


def _normalize(vector: List[float]) -> List[float]:
    """Scale to unit length, so cosine distance behaves in Chroma.

    EmbeddingGemma already returns unit vectors, which makes this a no-op there —
    but not every model does, and re-normalising costs nothing.
    """
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else list(vector)
