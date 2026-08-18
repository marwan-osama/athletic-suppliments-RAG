"""Stage 7 — search the index and return parent chunks.

A hit can be either a chunk or one of its generated questions. Both resolve to
the same parent chunk, so results are collapsed per chunk: without that, a single
passage can occupy all of the top-k slots through its own questions.
"""

from __future__ import annotations

from typing import Dict, List, Any

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
        llm_client: Any | None = None,  # Added LLM client for expansion
        num_expansions: int = 3,        # Number of queries to generate
    ):
        self.index = index
        self.top_k = top_k
        self.dedupe = dedupe
        self.overfetch = overfetch
        self.llm_client = llm_client
        self.num_expansions = num_expansions

    def expand_query(self, query: str) -> List[str]:
        """Generate alternative query formulations using the LLM."""
        if not self.llm_client:
            return [query]

        prompt = (
            f"Generate {self.num_expansions} different search queries based on the original user query. "
            "Use domain-specific terms, scientific synonyms, or rephrasings related to dietary supplements and athletic performance.\n"
            "Provide ONLY the expanded queries, one per line, without numbering or extra text.\n\n"
            f"Original query: {query}"
        )

        try:
            # Use the LLMClient.complete() method with temperature=0.7 for diverse expansions
            from .config import LLM_MODEL
            response = self.llm_client.complete(
                model=LLM_MODEL,
                prompt=prompt,
                temperature=0.7,  # Higher temp for diverse query variations
                max_tokens=200
            )
            expanded = [line.strip() for line in response.strip().split("\n") if line.strip()]
            # Return original + expansions, deduplicated
            all_queries = [query] + expanded
            return list(dict.fromkeys(all_queries))  # Preserve order, remove dupes
        except Exception as e:
            # Log error but gracefully fall back to original query
            return [query]

    def run(self, query: str, top_k: int | None = None) -> List[Retrieved]:
        k = top_k or self.top_k
        if not query.strip():
            return []

        # --- QUERY EXPANSION LAYER ---
        queries = self.expand_query(query)
        all_hits: List[Retrieved] = []

        # Retrieve candidates across all generated query variations
        for q in queries:
            vector = self.index.embedder.embed_query(q)
            raw = self.index.query(vector, n_results=k * self.overfetch if self.dedupe else k)
            all_hits.extend(self._to_hits(raw))

        # Collapse across expanded queries to deduplicate by parent chunk
        best = self._collapse(all_hits) if self.dedupe else all_hits
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
        """Keep the best-scoring hit per parent chunk.
        
        When a chunk is found via multiple query expansions, aggregate scores
        to give it a boost — multiple matches indicate high relevance.
        """
        best: Dict[str, Retrieved] = {}
        hit_counts: Dict[str, int] = {}
        
        for hit in hits:
            chunk_id = hit.chunk_id
            hit_counts[chunk_id] = hit_counts.get(chunk_id, 0) + 1
            current = best.get(chunk_id)
            
            if current is None or hit.similarity > current.similarity:
                best[chunk_id] = hit
        
        # Boost scores for chunks found in multiple expansions
        # (indicates convergence across query variations)
        for chunk_id, hit in best.items():
            if hit_counts[chunk_id] > 1:
                # Add a small boost: 5% per additional match, capped at +0.15
                boost = min(0.15, (hit_counts[chunk_id] - 1) * 0.05)
                hit.similarity = min(1.0, hit.similarity + boost)
        
        return list(best.values())