"""Stage 5 — hypothetical question generation.

Users ask questions; documents are written as statements. Indexing a few
plausible questions alongside each chunk gives the retriever question-shaped
text to match against, and each question points back to its parent chunk.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Sequence

from .llm import LLMClient
from .schema import Chunk, ProgressFn, Stage, report

_LIST_MARKER = re.compile(r"^(?:[-*•]+\s*)?(?:\d+[.)]\s+)?")


class QuestionGenerator(Stage):
    """Chunks in, `{chunk_id: [questions]}` out.

    Calls are independent, so they run on a small thread pool — generating for
    hundreds of chunks one at a time is what made indexing slow.
    """

    PROMPT = (
        "Given the following text about athletic performance and dietary supplements, "
        "generate {n} concise, natural questions that an athlete or health professional "
        "might ask. Focus on: efficacy, dosage, safety, side effects, and effects on performance.\n"
        "Return ONLY the questions, one per line, without numbering or bullets.\n\nText:\n{text}"
    )

    def __init__(
        self,
        client: LLMClient,
        model_name: str = "openai/gpt-oss-20b",
        num_questions: int = 3,
        workers: int = 8,
        temperature: float = 0.3,
        max_tokens: int = 1024,
        log: Callable[[str], None] = print,
    ):
        self.client = client
        self.model_name = model_name
        self.num_questions = num_questions
        self.workers = workers
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.log = log

    def run(
        self,
        chunks: Sequence[Chunk],
        on_progress: ProgressFn | None = None,
    ) -> Dict[str, List[str]]:
        if not chunks or self.num_questions <= 0:
            return {}

        questions: Dict[str, List[str]] = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            results = pool.map(lambda c: (c.id, self.for_text(c.text)), chunks)
            for done, (chunk_id, generated) in enumerate(results, start=1):
                if generated:
                    questions[chunk_id] = generated
                report(on_progress, done, len(chunks))
        return questions

    def for_text(self, text: str) -> List[str]:
        """Generate questions for a single passage; `[]` if the model fails."""
        try:
            raw = self.client.complete(
                model=self.model_name,
                prompt=self.PROMPT.format(n=self.num_questions, text=text),
                temperature=self.temperature,
                # Reasoning tokens are charged against max_tokens, so the budget
                # has to cover the thinking as well as the questions — too small
                # and the reply comes back empty. gpt-oss-20b barely thinks here
                # (~9 tokens), but other models spend hundreds.
                max_tokens=self.max_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - a chunk without questions is fine
            self.log(f"Skipping question generation ({exc})")
            return []

        return parse_questions(raw, limit=self.num_questions)


def parse_questions(raw: str, limit: int | None = None) -> List[str]:
    """One question per line, with bullets and numbering stripped."""
    questions = []
    for line in raw.splitlines():
        # Only leading list numbering — "100 mg of caffeine?" keeps its number.
        line = _LIST_MARKER.sub("", line.strip()).strip()
        if line:
            questions.append(line)
    return questions[:limit] if limit else questions
