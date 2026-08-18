"""Shared data types and the pipeline-stage protocol.

Every pipeline step is a callable object: it exposes `run()` for the real work,
`__call__()` so it can be used like a function, and `|` so steps compose into a
single callable chain (see `Chain`).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


# --------------------------------------------------------------------------- #
# Stage plumbing
# --------------------------------------------------------------------------- #
class Stage:
    """Base class for one step of the pipeline."""

    def run(self, value: Any) -> Any:  # pragma: no cover - overridden
        raise NotImplementedError

    def __call__(self, value: Any) -> Any:
        return self.run(value)

    def __or__(self, other: "Stage") -> "Chain":
        return Chain(self, other)

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"


class Chain(Stage):
    """`a | b` — feeds the output of each stage into the next."""

    def __init__(self, *stages: Stage):
        # Flatten so `a | b | c` stays a single list instead of nesting.
        self.stages: List[Stage] = []
        for stage in stages:
            self.stages.extend(stage.stages if isinstance(stage, Chain) else [stage])

    def run(self, value: Any) -> Any:
        for stage in self.stages:
            value = stage(value)
        return value

    def __repr__(self) -> str:
        return " | ".join(repr(s) for s in self.stages)


class Identity(Stage):
    """Passes its input straight through — how an optional stage is bypassed.

    `fetch | Identity() | chunk` keeps the shape of the pipeline intact when
    cleaning is switched off, so nothing downstream needs a `None` check.
    """

    def run(self, value: Any) -> Any:
        return value


ProgressFn = Callable[[int, int], None]


def report(on_progress: ProgressFn | None, done: int, total: int) -> None:
    """Call an optional progress callback without the caller needing a None check."""
    if on_progress is not None:
        on_progress(done, total)


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Chunk:
    """One retrievable passage of the source document."""

    index: int
    text: str
    section: str = ""

    @property
    def id(self) -> str:
        # Content-derived so re-indexing the same document overwrites the same
        # rows instead of piling up duplicates (upsert-friendly).
        digest = hashlib.sha1(self.text.encode("utf-8")).hexdigest()[:8]
        return f"c{self.index:04d}-{digest}"

    @property
    def size(self) -> int:
        return len(self.text)


@dataclass
class Retrieved:
    """A chunk that came back from a search, with why it matched."""

    chunk_id: str
    text: str
    similarity: float
    match_type: str  # "chunk" or "question"
    section: str = ""
    chunk_index: int = -1
    matched_text: str = ""  # the question that matched, when match_type == "question"

    @property
    def distance(self) -> float:
        return 1.0 - self.similarity


@dataclass
class BuildReport:
    """Outcome of an indexing run."""

    collection: str
    chunks: List[Chunk] = field(default_factory=list)
    questions: Dict[str, List[str]] = field(default_factory=dict)
    rows_indexed: int = 0
    skipped: bool = False

    @property
    def question_count(self) -> int:
        return sum(len(q) for q in self.questions.values())

    def summary(self) -> str:
        if self.skipped:
            return f"'{self.collection}' already indexed ({self.rows_indexed} rows)."
        return (
            f"Indexed {self.rows_indexed} rows into '{self.collection}': "
            f"{len(self.chunks)} chunks + {self.question_count} questions."
        )
