"""Stage 8 - Reranking search results.

Takes a pool of candidate chunks, passes them to the LLM for evaluation against
the query, and returns the top-K most relevant chunks based on the LLM's assessment.
"""

from __future__ import annotations

import json
import re
from typing import Callable, List, Optional

from .llm import LLMClient
from .schema import Retrieved, Stage


class LLMReranker(Stage):
    """Candidate Retrieved chunks in, smaller ranked list of Retrieved chunks out."""

    PROMPT = (
        "You are an expert search reranker. Given a user query and a list of candidate passages, "
        "your task is to select ONLY the passages that are genuinely relevant to answering the query.\n\n"
        "User Query: {query}\n\n"
        "Candidate Passages:\n{candidates}\n\n"
        "Return ONLY a JSON list of the integer indices of the relevant passages, ordered from most relevant to least relevant. "
        "You may return fewer than {k} indices if the other passages are not relevant, but do not return more than {k}. "
        "Do not include any other text. For example: [3, 0, 1]"
    )

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "openai/gpt-oss-20b",
        top_k: int = 5,
        temperature: float = 0.3,
        max_tokens: int = 100,
        reasoning_effort: str = "",
        log: Callable[[str], None] = print,
    ):
        self.client = client
        self.model_name = model_name
        self.top_k = top_k
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.log = log

    def run(self, query: str, candidates: List[Retrieved]) -> List[Retrieved]:
        """`candidates` is the list of results from retrieval; returns top-k."""
        if not candidates or self.top_k <= 0:
            return []
            
        if len(candidates) <= self.top_k:
            return candidates

        # Format the candidates with their indices
        formatted_candidates = "\n".join(
            f"[{i}] {hit.text}" for i, hit in enumerate(candidates)
        )

        try:
            raw = self.client.complete(
                model=self.model_name,
                prompt=self.PROMPT.format(
                    query=query,
                    candidates=formatted_candidates,
                    k=self.top_k,
                ),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort or None,
            )
            
            # Extract JSON list from the raw text using regex in case of markdown wrapping
            match = re.search(r'\[[\d\s,]+\]', raw)
            if not match:
                self.log(f"Reranker failed to return a JSON list: {raw[:100]}")
                return candidates[:self.top_k]
                
            indices = json.loads(match.group(0))
            
            # Filter and order the chunks
            reranked = []
            seen = set()
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                    reranked.append(candidates[idx])
                    seen.add(idx)
                    if len(reranked) == self.top_k:
                        break
                        
            # If the model returned fewer than requested, fill with remaining candidates
            if len(reranked) < self.top_k:
                for hit in candidates:
                    if hit not in reranked:
                        reranked.append(hit)
                        if len(reranked) == self.top_k:
                            break
                            
            return reranked

        except Exception as exc:
            self.log(f"Reranking failed ({exc}), falling back to original ordering")
            return candidates[:self.top_k]
