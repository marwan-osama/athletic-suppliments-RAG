"""Stage 8 — compose an answer from the retrieved chunks.

Each source is labelled with the page of the PDF it came from, and the model is
asked to cite that page alongside the source number.

Asking is not enough on its own — a small model will happily write a bare `[3]`,
or a page it liked the look of. So the citations it writes are rewritten against
`Retrieved.pages` afterwards: the page of source *n* is something this module
already knows, and looking it up is strictly better than trusting the model to
copy it. The model chooses which source supports a claim; the page that source
came from is not its to invent.

The refusal clause is deliberately narrow. An earlier wording asked the model to
refuse whenever the sources could not answer the question "fully", and on a
34-question evaluation that produced twelve refusals — nine of them on questions
the page does answer, one with perfect context recall. Multi-part and comparative
questions can almost never be answered "fully" from five chunks, so the model
declined instead of answering the part it had. Grounding is still strict; what
changed is that a partial answer now beats a refusal, and refusing is reserved
for retrieval that turned up nothing relevant at all.

Optional: retrieval quality is judged by looking at the chunks, and this step
costs an extra LLM call. The UI leaves it switched off by default.
"""

from __future__ import annotations

import re
from typing import Callable, Sequence

from .llm import LLMClient
from .schema import Retrieved

# `[3]` or `[3, p. 12]` — the source number is the part that matters; whatever
# the model put after it is replaced with the page that source really came from.
#
# Fullwidth brackets are accepted because models reach for them: gpt-oss-20b
# wrote `【4, p. 4】` in half the answers of one evaluation run. Matching only
# `[...]` let those through untouched, which is the one thing this must not do —
# an unrewritten citation is a page number the model chose, presented as if the
# index had confirmed it. The rewrite always emits the ASCII form.
CITATION = re.compile(r"[\[【]\s*(\d+)\s*(?:,[^\]】\n]*)?[\]】]")


class Answerer:
    """`answerer(question, chunks)` -> grounded answer text."""

    PROMPT = (
        "You are an assistant answering questions using ONLY the numbered sources "
        "below. Do NOT use outside knowledge, and do not infer or guess anything "
        "the sources do not state.\n\n"
        "Answer whatever the sources do support, and say plainly which part of the "
        "question they do not cover. A question with several parts, or one that "
        "asks you to compare two things, is answered from whichever sources apply "
        "to each part — a grounded partial answer is what is wanted, not a "
        "refusal.\n"
        "Reply with exactly \"I cannot answer this question based on the provided "
        "sources.\" only when the sources contain nothing bearing on the question "
        "at all.\n\n"
        "Each source is headed with the page of the document it was taken from. "
        "Cite every claim in square brackets with the source number and that page, "
        "exactly as [1, p. 12]. Use the page shown on the source you actually used "
        "— never guess a page, and never cite a page that is not shown below.\n\n"
        "Question: {question}\n\nSources:\n{sources}\n\nAnswer:"
    )

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "openai/gpt-oss-20b",
        temperature: float = 0.2,
        max_context_chars: int = 8_000,
        # Generous because this model's reasoning tokens come out of the same
        # budget as the answer itself.
        max_tokens: int = 2_048,
        reasoning_effort: str = "",
        log: Callable[[str], None] = print,
    ):
        self.client = client
        self.model_name = model_name
        self.temperature = temperature
        self.max_context_chars = max_context_chars
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.log = log

    def __call__(self, question: str, chunks: Sequence[Retrieved]) -> str:
        if not chunks:
            return "No sources retrieved — nothing to answer from."

        # Reasoning is left enabled here: unlike question generation, weighing
        # several sources against a question is what the model is good at.
        answer = self.client.complete(
            model=self.model_name,
            prompt=self.PROMPT.format(
                question=question, sources=self._format(chunks)
            ),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort or None,
        )
        return cite_pages(answer, chunks)

    def _format(self, chunks: Sequence[Retrieved]) -> str:
        blocks, used = [], 0
        for position, chunk in enumerate(chunks, start=1):
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break  # context budget spent
            text = chunk.text[:remaining]
            blocks.append(f"[{position}] {self._label(chunk)}\n{text}")
            used += len(text)
        return "\n\n".join(blocks)

    @staticmethod
    def _label(chunk: Retrieved) -> str:
        """`(Creatine > Efficacy, p. 12)` — what the model is asked to cite."""
        parts = [chunk.section or "document"]
        if chunk.pages_label:
            parts.append(chunk.pages_label)
        return f"({', '.join(parts)})"


def cite_pages(answer: str, chunks: Sequence[Retrieved]) -> str:
    """Rewrite every `[n]` citation to name the page source *n* came from.

    A citation pointing outside the source list is left exactly as it is: it is
    the model inventing a source, and quietly renumbering it would hide that.
    """

    def replace(match: "re.Match[str]") -> str:
        position = int(match.group(1))
        if not 1 <= position <= len(chunks):
            return match.group(0)
        label = chunks[position - 1].pages_label
        return f"[{position}, {label}]" if label else f"[{position}]"

    return CITATION.sub(replace, answer)
