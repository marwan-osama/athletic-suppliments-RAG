"""Stage 3 — split cleaned markdown into retrievable chunks.

Two things differ from a plain fixed-size split:

1. The document is cut at markdown headings first, so a chunk never straddles
   two topics (a "Creatine" chunk cannot bleed into "Ribose").
2. Each chunk carries its heading path. `#### Efficacy` on its own is useless in
   an index; "Creatine > Efficacy" tells both the embedder and the reader what
   the passage is about — which also removes the heading-only fragments that a
   naive split leaves behind.
"""

from __future__ import annotations

from typing import List, Tuple

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .preprocessing import split_heading
from .schema import Chunk, Stage

Section = Tuple[str, str]  # (heading path, body)


class MarkdownChunker(Stage):
    """Markdown in, list of `Chunk` out."""

    def __init__(
        self,
        chunk_size: int = 600,
        chunk_overlap: int = 100,
        min_chars: int = 80,
        prepend_section: bool = True,
        max_section_chars: int = 80,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chars = min_chars
        self.prepend_section = prepend_section
        self.max_section_chars = max_section_chars

    def run(self, markdown: str) -> List[Chunk]:
        chunks: List[Chunk] = []
        for section, body in self._split_sections(markdown):
            prefix = self._prefix(section)
            for piece in self._split_body(body, reserved=len(prefix)):
                chunks.append(
                    Chunk(index=len(chunks), text=prefix + piece, section=section)
                )
        return chunks

    def _prefix(self, section: str) -> str:
        """The in-text heading path, capped so it can never crowd out the body.

        Without a cap, a long heading plus a small chunk size would push chunks
        past `chunk_size`. The full path is still kept in `Chunk.section`.
        """
        if not (self.prepend_section and section):
            return ""
        budget = max(self.chunk_size // 3, 20)
        if len(section) > budget:
            section = section[: budget - 1].rstrip() + "…"
        return f"{section}\n\n"

    # -- sections ----------------------------------------------------------- #
    def _split_sections(self, markdown: str) -> List[Section]:
        sections: List[Section] = []
        stack: List[Tuple[int, str]] = []  # (heading level, title)
        body: List[str] = []

        def flush() -> None:
            text = "\n".join(body).strip()
            if text:
                sections.append((self._breadcrumb(stack), text))
            body.clear()

        for line in markdown.splitlines():
            level, title = split_heading(line)
            if level and title:
                flush()
                # Pop siblings and deeper headings, then push this one.
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, title))
            else:
                body.append(line)
        flush()
        return sections

    def _breadcrumb(self, stack: List[Tuple[int, str]]) -> str:
        """Heading path, trimmed from the outside in so it stays short.

        The `# ` title is the same on every chunk of the document, so it carries
        no information about a passage — it is dropped whenever a deeper heading
        exists. Remaining outer levels ("Selected Ingredients in Dietary
        Supplements for…") are dropped until the path fits `max_section_chars`,
        which leaves the part that identifies the passage: "Creatine > Efficacy".
        """
        # Fall back to the title for text that sits above any deeper heading.
        titles = [title for level, title in stack if level > 1] or [
            title for _, title in stack
        ]
        while len(titles) > 1 and len(" > ".join(titles)) > self.max_section_chars:
            titles.pop(0)
        return " > ".join(titles)

    # -- bodies ------------------------------------------------------------- #
    def _split_body(self, body: str, reserved: int = 0) -> List[str]:
        # Keep the heading path inside the size budget so a chunk never exceeds
        # the size the user asked for.
        size = max(self.chunk_size - reserved, self.chunk_size // 2)
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=size,
            chunk_overlap=min(self.chunk_overlap, size // 2),
            length_function=len,
            separators=["\n\n", "\n", " ", ""],
        )
        return self._merge_small(splitter.split_text(body), budget=size)

    def _merge_small(self, pieces: List[str], budget: int) -> List[str]:
        """Fold fragments below `min_chars` into a neighbour, when they fit.

        Merging is skipped rather than allowed to push a chunk past `budget` —
        the size the user asked for is the promise the diagnostics check.
        """

        def fits(left: str, right: str) -> bool:
            return len(left) + len(right) + 1 <= budget

        merged: List[str] = []
        for piece in (p.strip() for p in pieces):
            if not piece or not any(ch.isalnum() for ch in piece):
                continue
            if merged and len(piece) < self.min_chars and fits(merged[-1], piece):
                merged[-1] = f"{merged[-1]}\n{piece}"
            else:
                merged.append(piece)

        # A lone opening fragment has no previous neighbour to merge into.
        if len(merged) > 1 and len(merged[0]) < self.min_chars and fits(*merged[:2]):
            merged[1] = f"{merged[0]}\n{merged[1]}"
            merged.pop(0)
        return merged
