"""Stage 7 — search the index and return parent chunks.

A hit can be either a chunk or one of its generated questions. Both resolve to
the same parent chunk, so results are collapsed per chunk: without that, a single
passage can occupy all of the top-k slots through its own questions.
"""

from __future__ import annotations

from typing import Dict, List

from .indexing import QUESTION_ROW, VectorIndex
from .schema import Retrieved, Stage


class Retriever(Stage):
    """Query string in, ranked `Retrieved` chunks out."""

    def __init__(
        self,
        index: VectorIndex,
        top_k: int = 5,
        dedupe: bool = True,
        overfetch: int = 3,
    ):
        self.index = index
        self.top_k = top_k
        self.dedupe = dedupe
        self.overfetch = overfetch

    def run(self, query: str, top_k: int | None = None) -> List[Retrieved]:
        k = top_k or self.top_k
        if not query.strip():
            return []

        # Embed with RETRIEVAL_QUERY rather than RETRIEVAL_DOCUMENT.
        vector = self.index.embedder.embed_query(query)
        raw = self.index.query(vector, n_results=k * self.overfetch if self.dedupe else k)

        hits = self._to_hits(raw)
        best = self._collapse(hits) if self.dedupe else hits
        best.sort(key=lambda hit: hit.similarity, reverse=True)
        results = best[:k]

        # Question hits carry only a parent pointer — fill in the parent text.
        texts = self.index.texts_for(
            hit.chunk_id for hit in results if hit.match_type == QUESTION_ROW
        )
        for hit in results:
            hit.text = texts.get(hit.chunk_id, hit.text)
        return results

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _to_hits(raw: Dict) -> List[Retrieved]:
        ids = raw["ids"][0]
        documents = raw["documents"][0]
        metadatas = raw["metadatas"][0]
        distances = (raw.get("distances") or [[None] * len(ids)])[0]

        hits = []
        for row_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            metadata = metadata or {}
            match_type = metadata.get("type", "chunk")
            hits.append(
                Retrieved(
                    chunk_id=metadata.get("parent_id", row_id),
                    text=document,
                    similarity=1.0 - distance if distance is not None else 0.0,
                    match_type=match_type,
                    section=metadata.get("section", ""),
                    chunk_index=int(metadata.get("chunk_index", -1)),
                    matched_text=document if match_type == QUESTION_ROW else "",
                )
            )
        return hits

    @staticmethod
    def _collapse(hits: List[Retrieved]) -> List[Retrieved]:
        """Keep the best-scoring hit per parent chunk."""
        best: Dict[str, Retrieved] = {}
        for hit in hits:
            current = best.get(hit.chunk_id)
            if current is None or hit.similarity > current.similarity:
                best[hit.chunk_id] = hit
        return list(best.values())
