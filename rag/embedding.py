"""Stage 4 — text to vectors, via an OpenRouter embedding model."""

from __future__ import annotations

import hashlib
import math
from typing import List, Sequence

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from .openrouter import OpenRouterClient
from .utils import batched


class OpenRouterEmbedder(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by OpenRouter.

    `nvidia/llama-nemotron-embed-vl-1b-v2` is asymmetric: it is trained with a
    `query:` prefix on searches and a `passage:` prefix on documents (its chat
    template adds them from the message role). OpenRouter's OpenAI-shaped
    endpoint has no role field, so the prefixes are applied here — `__call__`
    embeds passages, `embed_query` embeds queries. Set the prefixes to "" to
    switch this off for a symmetric model.
    """

    # What the model returns (mean-pooled). Informational: the endpoint has no
    # dimensions parameter to change it.
    MODEL_DIMENSIONS = 2048

    def __init__(
        self,
        client: OpenRouterClient,
        model_name: str = "nvidia/llama-nemotron-embed-vl-1b-v2:free",
        batch_size: int = 16,
        document_prefix: str = "passage: ",
        query_prefix: str = "query: ",
    ):
        self.client = client
        self.model_name = model_name
        self.batch_size = batch_size
        self.document_prefix = document_prefix
        self.query_prefix = query_prefix

    @staticmethod
    def name() -> str:
        # Lets Chroma persist/identify the EF config without warnings.
        return "openrouter_embedding_fn"

    @property
    def dimensions(self) -> int:
        return self.MODEL_DIMENSIONS

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
    """Offline stand-in: deterministic bag-of-words vectors, no API key needed.

    Retrieval quality is poor (it only matches shared words), but it makes the UI
    and the tests runnable without credentials or network access.
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
    """Scale to unit length.

    The model mean-pools token embeddings and does not promise unit vectors, so
    normalising here is what makes cosine distance behave in Chroma.
    """
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else list(vector)
