"""Stage 7a — query expansion, ahead of retrieval.

A passage worded differently from the question can be missed however good the
embedder is: "does creatine help sprinting" and "phosphocreatine resynthesis in
repeated high-intensity efforts" are the same question in different vocabularies.
Asking the model for a few other phrasings and retrieving for each widens the net,
and a chunk that several phrasings agree on is more likely to be the right one.

Optional, and off the same switch as the rest: it costs one generation call per
search, so it trades latency for recall.
"""

from __future__ import annotations

from typing import Callable, List

from .llm import LLMClient
from .schema import Stage
from .utils import parse_lines


class QueryExpander(Stage):
    """A query in, that query plus alternative phrasings out.

    The original is always first and always kept, so a failed generation — or a
    model that answers with nothing usable — degrades to plain retrieval rather
    than to no retrieval at all.
    """

    PROMPT = (
        "Generate {n} alternative search queries for the query below, which is "
        "about dietary supplements and athletic performance. Use domain terms, "
        "scientific synonyms and rephrasings.\n"
        "Return ONLY the queries, one per line, without numbering.\n\n"
        "Query: {query}"
    )

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "openai/gpt-oss-20b",
        num_expansions: int = 2,
        # Higher than the other stages on purpose: phrasings that differ from
        # each other are the whole point, and a near-copy of the query buys
        # nothing.
        temperature: float = 0.7,
        max_tokens: int = 1_024,
        reasoning_effort: str = "",
        log: Callable[[str], None] = print,
    ):
        self.client = client
        self.model_name = model_name
        self.num_expansions = num_expansions
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.log = log

    def run(self, query: str) -> List[str]:
        """`[query, *phrasings]`, deduplicated, original first."""
        if self.num_expansions <= 0 or not query.strip():
            return [query]

        try:
            raw = self.client.complete(
                model=self.model_name,
                prompt=self.PROMPT.format(n=self.num_expansions, query=query),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort or None,
            )
        except Exception as exc:  # noqa: BLE001 - a search without extra phrasings is fine
            self.log(f"Skipping query expansion ({exc})")
            return [query]

        phrasings = parse_lines(raw, limit=self.num_expansions)
        # dict.fromkeys keeps order, so the original stays the first phrasing.
        return list(dict.fromkeys([query, *phrasings]))
