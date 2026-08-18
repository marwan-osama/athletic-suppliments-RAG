"""Stage 7 — search the index and return parent chunks.

A hit can be either a chunk or one of its generated questions. Both resolve to
the same parent chunk, so results are collapsed per chunk: without that, a single
passage can occupy all of the top-k slots through its own questions.

When query expansion is on, the search runs once per phrasing and the results are
merged. Agreement between phrasings is evidence: a chunk several of them found
gets a boost, applied to `Retrieved.score` so that `similarity` stays the number
the embedder actually returned.
"""

from __future__ import annotations

from typing import Callable, Dict, Hashable, List, Optional

from .expansion import QueryExpander
from .indexing import QUESTION_ROW, VectorIndex
from .schema import Retrieved, Stage

# What counts as "the same result", per dedupe mode. Collapsing by parent chunk
# folds a chunk and its questions together; without it they stay separate results
# and only genuinely repeated rows are dropped.
BY_CHUNK: Callable[[Retrieved], Hashable] = lambda hit: hit.chunk_id
BY_ROW: Callable[[Retrieved], Hashable] = lambda hit: (hit.chunk_id, hit.matched_text)


class Retriever(Stage):
    """Query string in, ranked `Retrieved` chunks out."""

    def __init__(
        self,
        index: VectorIndex,
        top_k: int = 5,
        dedupe: bool = True,
        overfetch: int = 3,
        expander: Optional[QueryExpander] = None,
        match_boost: float = 0.05,
        match_boost_cap: float = 0.15,
    ):
        self.index = index
        self.top_k = top_k
        self.dedupe = dedupe
        self.overfetch = overfetch
        self.expander = expander
        self.match_boost = match_boost
        self.match_boost_cap = match_boost_cap

    def run(self, query: str, top_k: int | None = None) -> List[Retrieved]:
        k = top_k or self.top_k
        if not query.strip():
            return []

        phrasings = self.expander(query) if self.expander else [query]
        n_results = k * self.overfetch if self.dedupe else k

        # Kept per phrasing rather than in one flat list: agreement is counted
        # one vote per phrasing, so a chunk that matched through three of its own
        # questions is still a single vote.
        found = [
            self._to_hits(self.index.query(self._vector(phrasing), n_results))
            for phrasing in phrasings
        ]

        best = self._merge(found, BY_CHUNK if self.dedupe else BY_ROW)
        best.sort(key=lambda hit: hit.score, reverse=True)
        results = best[:k]

        # Question hits carry only a parent pointer — fill in the parent text.
        texts = self.index.texts_for(
            hit.chunk_id for hit in results if hit.match_type == QUESTION_ROW
        )
        for hit in results:
            hit.text = texts.get(hit.chunk_id, hit.text)
        return results

    # -- internals ---------------------------------------------------------- #
    def _vector(self, query: str) -> List[float]:
        # Embed with RETRIEVAL_QUERY rather than RETRIEVAL_DOCUMENT.
        return self.index.embedder.embed_query(query)

    def _merge(
        self,
        found: List[List[Retrieved]],
        identity: Callable[[Retrieved], Hashable],
    ) -> List[Retrieved]:
        """Keep the best hit per identity, and record how many phrasings found it.

        `similarity` is left as it came back from the index; the agreement bonus
        goes to `boost`, which only `score` reads. A result never claims to be a
        closer match than it was.
        """
        best: Dict[Hashable, Retrieved] = {}
        votes: Dict[Hashable, int] = {}

        for hits in found:
            counted: set = set()
            for hit in hits:
                key = identity(hit)
                if key not in counted:  # one vote per phrasing, not per row
                    counted.add(key)
                    votes[key] = votes.get(key, 0) + 1
                current = best.get(key)
                if current is None or hit.similarity > current.similarity:
                    best[key] = hit

        for key, hit in best.items():
            hit.matches = votes[key]
            hit.boost = min(self.match_boost_cap, (hit.matches - 1) * self.match_boost)
        return list(best.values())

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
