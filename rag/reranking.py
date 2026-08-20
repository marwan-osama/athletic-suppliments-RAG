"""Stage 7b — reorder retrieved chunks by asking the model to judge them.

The embedder scores a question against a passage separately: each is turned into
a vector without ever seeing the other, and the match is whatever the geometry
says. A reranker reads the two together, which is why it can tell a passage that
shares vocabulary with the question from one that actually answers it.

Measured on this corpus, that is where the value is. Querying the index with each
golden reference answer locates the passages retrieval ought to surface; 45% of
them already sit in the dense top 5, **41% sit at ranks 6-20**, and only 14% are
missed by the top 20 altogether. The evidence is being found and then ranked too
low — which is a reordering problem, not a recall problem.

Listwise, not pointwise: every candidate goes into one prompt and the model
returns an order, so a search costs one generation call rather than one per
candidate — the same budget `QueryExpander` already spends.

Two rules keep a bad reply from costing results:

* It **reorders, never filters.** Candidates the model leaves out keep their
  dense order and follow the ones it chose. Truncation to `top_k` happens in the
  retriever afterwards, so the reranker decides which chunks reach the answer but
  can never shrink the result set below what dense retrieval found.
* Anything unusable is ignored. Out-of-range numbers, repeats and a failed call
  all degrade to the dense order rather than to an empty list. The call is tried
  twice before giving up: the local server intermittently returns an empty reply,
  and a fallback that costs the whole ranking is worth one extra attempt.
"""

from __future__ import annotations

import re
from typing import Callable, List, Sequence

from .llm import LLMClient
from .schema import Retrieved

_NUMBER = re.compile(r"\d+")


class Reranker:
    """`reranker(question, hits)` -> the same hits, best first."""

    # Asking for a target count rather than "leave out the irrelevant ones":
    # phrased as a filter, gpt-oss-20b returned as little as a single number, so
    # only the top slot was ever reranked and the rest stayed in dense order.
    PROMPT = (
        "Rank the passages below by how well they help answer the question.\n\n"
        "Return the {want} most useful passage numbers, best first, as a "
        "comma-separated list — for example: 4, 1, 7\n"
        "Judge whether a passage actually answers the question, not whether it "
        "shares words with it. Put passages that are about the subject but "
        "answer nothing at the end. Return ONLY the numbers.\n\n"
        "Question: {question}\n\nPassages:\n{passages}\n\nRanking:"
    )

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.0,  # an ordering should not vary between runs
        # Generous: this model's reasoning comes out of the same budget, and a
        # truncated reply is an empty ranking.
        max_tokens: int = 2_048,
        snippet_chars: int = 400,
        reasoning_effort: str = "",
        log: Callable[[str], None] = print,
    ):
        self.client = client
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.snippet_chars = snippet_chars
        self.reasoning_effort = reasoning_effort
        self.log = log

    def __call__(
        self, question: str, hits: Sequence[Retrieved], want: int = 0
    ) -> List[Retrieved]:
        """`want` is how many the caller will keep — the rest still come back."""
        hits = list(hits)
        # Nothing to reorder, and no call worth paying for.
        if len(hits) < 2 or not question.strip():
            return hits

        # Recorded before anything moves, so the UI can show what the rerank did.
        for position, hit in enumerate(hits, start=1):
            hit.dense_rank = position

        prompt = self.PROMPT.format(
            question=question,
            want=min(want or len(hits), len(hits)),
            passages=self._format(hits),
        )

        # One retry, because the failure this guards against is transient. A
        # flaky server returned an empty reply for 5 of 34 searches in one run
        # and none of 8 minutes later, at identical settings — so the second
        # attempt is worth more here than any prompt or temperature change.
        order: List[int] = []
        for attempt in (1, 2):
            try:
                raw = self.client.complete(
                    model=self.model_name,
                    prompt=prompt,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort or None,
                )
            except Exception as exc:  # noqa: BLE001 - dense order is a fine answer
                if attempt == 2:
                    self.log(f"Skipping rerank ({exc})")
                    return hits
                continue
            order = parse_ranking(raw, len(hits))
            if order:
                break

        if not order:
            self.log("Skipping rerank (no usable ranking returned)")
            return hits

        chosen = [hits[index] for index in order]
        rest = [hit for position, hit in enumerate(hits) if position not in set(order)]
        return chosen + rest

    # -- internals ---------------------------------------------------------- #
    def _format(self, hits: Sequence[Retrieved]) -> str:
        blocks = []
        for position, hit in enumerate(hits, start=1):
            head = hit.section or "document"
            blocks.append(f"[{position}] ({head})\n{hit.text[: self.snippet_chars]}")
        return "\n\n".join(blocks)


def parse_ranking(raw: str, count: int) -> List[int]:
    """Model reply -> zero-based positions, in the order it gave them.

    Repeats and numbers outside `1..count` are dropped rather than clamped: a
    number the model invented says nothing about which passage it meant.
    """
    seen, order = set(), []
    for match in _NUMBER.findall(raw or ""):
        index = int(match) - 1
        if 0 <= index < count and index not in seen:
            seen.add(index)
            order.append(index)
    return order
