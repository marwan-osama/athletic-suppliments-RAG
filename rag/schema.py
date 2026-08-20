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
def page_label(pages: "tuple[int, ...]") -> str:
    """Pages as a citation: `()` -> "", `(7,)` -> "p. 7", `(7, 8)` -> "pp. 7-8".

    A run of consecutive pages is written as a range; a chunk that somehow spans
    a gap keeps every page listed, because dropping one would misattribute it.
    """
    if not pages:
        return ""
    if len(pages) == 1:
        return f"p. {pages[0]}"
    if list(pages) == list(range(pages[0], pages[-1] + 1)):
        return f"pp. {pages[0]}-{pages[-1]}"
    return "pp. " + ", ".join(str(page) for page in pages)


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage of the source document."""

    index: int
    text: str
    section: str = ""
    # Which page(s) of the PDF this passage came from. Recovered from the
    # markers `PdfReader` leaves in the markdown, so a citation can name a page.
    pages: tuple = ()

    @property
    def pages_label(self) -> str:
        return page_label(self.pages)

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
    # How many query phrasings found this chunk, and the ranking bonus that
    # earned it. Both are 1 and 0.0 without query expansion.
    matches: int = 1
    boost: float = 0.0
    # Page(s) of the source PDF, carried through the index so an answer can cite
    # where it came from.
    pages: tuple = ()
    # Where this hit sat in the dense ranking before the reranker moved it, and
    # where it ended up — both 1-based; `dense_rank` is -1 when nothing reranked.
    # Kept separate from `score` so the number shown beside a result stays the
    # one the embedder returned.
    dense_rank: int = -1
    rank: int = 0

    @property
    def pages_label(self) -> str:
        return page_label(self.pages)

    @property
    def rerank_move(self) -> int:
        """Places gained by reranking — positive is a promotion, 0 if unranked."""
        if self.dense_rank < 0 or not self.rank:
            return 0
        return self.dense_rank - self.rank

    @property
    def distance(self) -> float:
        return 1.0 - self.similarity

    @property
    def score(self) -> float:
        """What ranking sorts by: the match, plus what agreement it attracted.

        Separate from `similarity` on purpose — the number shown next to a
        result is always the one the embedder returned, so a boosted chunk can
        never look like a closer match than it was.
        """
        return min(1.0, self.similarity + self.boost)


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
