"""Stage 2 — clean the extracted markdown before chunking.

What `PdfReader` hands over still carries things that hurt retrieval: numbered
citations left in the prose, web chrome that was on the page when the document
was typeset, and whole sections (the 200-entry reference list) that are nothing
but numbers and names. Left alone, chunks end up made of them.

Page markers pass through untouched: an HTML comment matches none of the
patterns here, which is what lets provenance survive a stage that rewrites
almost every other character.
"""

from __future__ import annotations

import re
from typing import List, Sequence, Tuple

from .schema import Stage

# `[label](url)` -> `label`. The label pattern excludes brackets so that nested
# links unwrap correctly when the substitution is applied repeatedly.
_LINK = re.compile(r"\[([^\[\]]*)\]\((?:[^()]*(?:\([^()]*\)[^()]*)*)\)")
_BARE_URL = re.compile(r"https?://\S+")
_CITATION = re.compile(r"\[\s*\d+(?:\s*[,–-]\s*\d+)*\s*\]")
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_BLANK_RUN = re.compile(r"\n{3,}")
_SPACE_RUN = re.compile(r"[ \t]{2,}")
_HEADING = re.compile(r"^(#{1,6})\s*(.*?)\s*#*$")
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:)])")
# Unwrapping adjacent links strands emphasis markers: `Q10****CoQ10`.
_ASTERISK_RUN = re.compile(r"\*{3,}")


def split_heading(line: str) -> Tuple[int, str]:
    """`('### Efficacy')` -> `(3, 'Efficacy')`; `(0, '')` for non-headings."""
    match = _HEADING.match(line.strip())
    return (len(match.group(1)), match.group(2)) if match else (0, "")

# Where the subject of a sentence ends: "HMB is a metabolite…" -> "HMB",
# "Betaine, also known as…" -> "Betaine".
_TITLE_STOP = re.compile(
    r"\b(?:is|are|was|were|has|have|can|may|might|refers|consists|occurs|"
    r"includes|comes|and|or|also|which|that)\b|[,:;(\[–—]"
)

# Navigation / chrome that was on the page when it was typeset, not article text.
_BOILERPLATE = (
    "ask ods",
    "have a question",
    "join the",
    "ods email list",
    "email list",
    "skip to",
    "print this",
    "share this",
    "back to top",
    "consumer",
    "health professional",
    "other resources",
    "subscribe",
)


class MarkdownCleaner(Stage):
    """Markdown in, tidier markdown out."""

    def __init__(
        self,
        strip_links: bool = True,
        strip_citations: bool = True,
        drop_boilerplate: bool = True,
        name_empty_headings: bool = True,
        drop_sections: Sequence[str] = ("references", "disclaimer"),
    ):
        self.strip_links = strip_links
        self.strip_citations = strip_citations
        self.drop_boilerplate = drop_boilerplate
        self.name_empty_headings = name_empty_headings
        self.drop_sections = tuple(s.lower() for s in drop_sections)

    def run(self, markdown: str) -> str:
        # Escaped brackets first: `[\[CoQ](url)` only parses as a link once the
        # backslash-escaped brackets inside its label are gone.
        text = markdown.replace("\\[", "").replace("\\]", "")

        if self.strip_links:
            text = self._unwrap_links(text)
        text = _HTML_TAG.sub("", text)
        if self.strip_citations:
            text = _CITATION.sub("", text)
        # Removing links and citations leaves "text .", "(see )" and `****`.
        text = _ASTERISK_RUN.sub(" ", text)
        text = _EMPTY_PARENS.sub("", _SPACE_BEFORE_PUNCT.sub(r"\1", text))
        if self.drop_sections:
            text = self._drop_sections(text)

        # Naming comes before line tidying, which would otherwise have already
        # discarded the empty headings this repairs.
        lines = text.splitlines()
        if self.name_empty_headings:
            lines = self._name_headings(lines)
        kept = [
            tidied
            for tidied in (self._tidy_line(line) for line in lines)
            if tidied is not None
        ]

        return _BLANK_RUN.sub("\n\n", "\n".join(kept)).strip() + "\n"

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _unwrap_links(text: str) -> str:
        # Repeat until stable: the source nests links inside link labels.
        for _ in range(6):
            unwrapped = _LINK.sub(r"\1", text)
            if unwrapped == text:
                break
            text = unwrapped
        return _BARE_URL.sub("", text)

    def _drop_sections(self, text: str) -> str:
        """Remove whole sections (e.g. the 100+ entry reference list)."""
        kept: list[str] = []
        skipping_at: int | None = None

        for line in text.splitlines():
            level, title = split_heading(line)
            if level:
                if skipping_at is not None and level <= skipping_at:
                    skipping_at = None  # section ended
                if skipping_at is None and title.lower().strip(": ") in self.drop_sections:
                    skipping_at = level
                    continue
            if skipping_at is None:
                kept.append(line)
        return "\n".join(kept)

    def _name_headings(self, lines: List[str]) -> List[str]:
        """Give a name to headings that arrived empty.

        A heading can arrive with no text of its own — a glyph the extractor
        could not map, or a name that lived in an image. Without a name, each
        subsection below it reads only "Efficacy" or "Implications for use", and
        the passage no longer says which supplement it is about. The first
        sentence of the section always opens with the name ("HMB is a metabolite
        of…"), so it is recovered from there.
        """
        named: List[str] = []
        for position, line in enumerate(lines):
            level, title = split_heading(line)
            # `### ` and `### 10)` are both nameless: neither says anything.
            if level and not any(character.isalpha() for character in title):
                inferred = self._infer_title(lines[position + 1 :])
                if not inferred:
                    continue  # nothing to name it after — drop the heading
                line = f"{'#' * level} {inferred}"
            named.append(line)
        return named

    @staticmethod
    def _infer_title(following: List[str]) -> str:
        """The subject of the next paragraph, or "" if the next line is a heading."""
        for line in following:
            if not line.strip():
                continue
            if split_heading(line)[0]:
                return ""  # a heading follows directly: no body to name it after
            subject = _TITLE_STOP.split(line.strip(), 1)[0]
            words = subject.strip(" .*_|").split()
            if not words or not words[0][:1].isalpha() or len(words) > 5:
                return ""
            return " ".join(words)[:40]
        return ""

    def _tidy_line(self, line: str) -> str | None:
        """Normalise one line; return None to drop it, "" to keep a blank."""
        line = _SPACE_RUN.sub(" ", line).rstrip()
        stripped = line.strip()

        if not stripped:
            return ""  # paragraph break
        # Bullets, bare heading marks, and table rows left empty once their
        # links were removed — but keep table rules like `|---|---|`.
        if set(stripped) <= set("#-*| "):
            return line if stripped.startswith("|-") else None
        # `### 10)` — what is left of "coenzyme Q<sub>10</sub>" once the tags are
        # gone. A heading with no letters names nothing, and it would otherwise
        # add a meaningless level to every heading path beneath it.
        level, title = split_heading(stripped)
        if level and not any(character.isalpha() for character in title):
            return None
        if self.drop_boilerplate and self._is_boilerplate(stripped):
            return None
        return line

    @staticmethod
    def _is_boilerplate(stripped: str) -> bool:
        # Only short standalone lines — never a sentence that merely mentions one
        # of these phrases.
        if len(stripped) > 60 or stripped.startswith("#"):
            return False
        text = stripped.lstrip("-*| ").rstrip("| ").lower()
        return any(text.startswith(prefix) for prefix in _BOILERPLATE)
