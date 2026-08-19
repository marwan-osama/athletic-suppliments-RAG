"""Stage 8 — compose an answer from the retrieved chunks.

Optional: retrieval quality is judged by looking at the chunks, and this step
costs an extra LLM call. The UI leaves it switched off by default.
"""

from __future__ import annotations

from typing import Callable, Sequence

from .llm import LLMClient
from .schema import Retrieved


class Answerer:
    """`answerer(question, chunks)` -> grounded answer text."""

    PROMPT = (
        "You are an assistant answering questions based STRICTLY on the provided sources. "
        "Your task is to answer the question using ONLY the numbered sources below. "
        "You must NOT use any outside knowledge. "
        "If the provided sources do not contain enough information to fully and accurately answer the question, "
        "you MUST explicitly say: \"I cannot answer this question based on the provided sources.\" "
        "Do not attempt to infer or guess answers that are not explicitly stated in the sources.\n\n"
        "Cite the sources you use as [1], [2], and so on.\n\n"
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
        return self.client.complete(
            model=self.model_name,
            prompt=self.PROMPT.format(
                question=question, sources=self._format(chunks)
            ),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort or None,
        )

    def _format(self, chunks: Sequence[Retrieved]) -> str:
        blocks, used = [], 0
        for position, chunk in enumerate(chunks, start=1):
            remaining = self.max_context_chars - used
            if remaining <= 0:
                break  # context budget spent
            text = chunk.text[:remaining]
            blocks.append(f"[{position}] ({chunk.section or 'document'})\n{text}")
            used += len(text)
        return "\n\n".join(blocks)
