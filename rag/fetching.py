"""Stage 1 — turn a PDF into markdown, with the page each passage came from.

A PDF carries no headings, no paragraphs and no reading order — only glyphs at
coordinates. Two things have to be recovered before the rest of the pipeline
can work the way it already does:

1. **Structure.** Font size is the one structural signal that survives into the
   file, so the distinct sizes above the body size are ranked and mapped onto
   heading levels. That hands `MarkdownChunker` the `#` marks it already splits
   on, which is what keeps "Creatine > Efficacy" breadcrumbs working.
2. **Page numbers.** Every page's text is preceded by a `<!--page:N-->` marker.
   It rides through cleaning untouched (an HTML comment matches none of the
   cleaner's patterns) and is read and stripped by the chunker, which is how a
   retrieved chunk can say which page it came from.

Extraction is slow, so the markdown is cached on disk and reused unless
`use_cache=False`.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple, Union

import pdfplumber

from .schema import Stage

# What the chunker reads page provenance back out of. An HTML comment on purpose:
# `MarkdownCleaner` strips `<tag>` but never `<!-- -->`, so the marker survives a
# stage that rewrites almost everything else.
PAGE_MARKER = "<!--page:{page}-->"
PAGE_PATTERN = re.compile(r"<!--page:(\d+)-->")

# A line this much wider than the widest gap to the right margin is mid-paragraph;
# a shorter one ended its paragraph. Points, and forgiving — justified text does
# not reach the exact same x on every line.
PARAGRAPH_SLACK = 12.0

# Fraction of the page height at the top and bottom that counts as margin, where
# running heads and folios live.
MARGIN_BAND = 0.08

BULLET_GLYPHS = "•◦‣▪–·"

# pdfminer emits `(cid:N)` for a glyph it cannot map to Unicode — symbol-font
# bullets, mostly. Turned into a real bullet so list items survive as list items.
_CID = re.compile(r"\(cid:(\d+)\)")


class PdfReader(Stage):
    """PDF path in, markdown (with page markers) out.

    `min_chars` guards the case that looks like success and is not: a scanned
    PDF with no text layer extracts to almost nothing, and every stage after
    this one would happily index the emptiness.
    """

    def __init__(
        self,
        cache_dir: Union[str, Path] = ".cache",
        use_cache: bool = True,
        min_chars: int = 1_000,
        heading_levels: int = 4,
        drop_repeated_lines: bool = True,
    ):
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.min_chars = min_chars
        self.heading_levels = heading_levels
        self.drop_repeated_lines = drop_repeated_lines

    def run(self, source: Union[str, Path]) -> str:
        path = Path(str(source)).expanduser()
        # Checked before the cache, not after: a cache entry left by some other
        # kind of source would otherwise be served as though it came from a PDF,
        # and the mismatch would only surface as missing page numbers much later.
        if path.suffix.lower() != ".pdf":
            raise ValueError(
                f"{path.name!r} is not a PDF — this pipeline indexes PDFs. "
                "Point RAG_SOURCE at a .pdf file."
            )

        cache_path = self._cache_path(source)
        if self.use_cache and cache_path.is_file():
            return cache_path.read_text(encoding="utf-8")

        if not path.is_file():
            raise FileNotFoundError(f"No such PDF: {path}")

        markdown = self._extract(path)
        if len(markdown) < self.min_chars:
            raise ValueError(
                f"Extraction produced {len(markdown)} chars from {path.name} "
                f"(expected at least {self.min_chars}) — the PDF may be a scan "
                "with no text layer."
            )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(markdown, encoding="utf-8")
        return markdown

    # -- extraction --------------------------------------------------------- #
    def _extract(self, path: Path) -> str:
        with pdfplumber.open(str(path)) as pdf:
            pages = [self._lines(page) for page in pdf.pages]

        body_size = self._body_size(pages)
        levels = self._heading_levels(pages, body_size)
        boilerplate = self._repeated(pages) if self.drop_repeated_lines else set()

        out: List[str] = []
        for number, lines in enumerate(pages, start=1):
            out.append(PAGE_MARKER.format(page=number))
            out.extend(self._render(lines, body_size, levels, boilerplate))
        return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"

    @staticmethod
    def _lines(page) -> List[Dict]:
        """One dict per visual line: text, dominant size, boldness, geometry."""
        lines = []
        height = float(page.height) or 1.0
        for line in page.extract_text_lines(strip=True, return_chars=True):
            text = _decode_glyphs(line["text"].strip())
            chars = line.get("chars") or []
            if not text or not chars:
                continue
            sizes = Counter(round(char["size"], 1) for char in chars)
            fonts = Counter(char["fontname"] for char in chars)
            lines.append(
                {
                    "text": text,
                    "size": sizes.most_common(1)[0][0],
                    "bold": "bold" in fonts.most_common(1)[0][0].lower(),
                    "x1": line["x1"],
                    # Fraction down the page — how a running head is told from a
                    # heading that merely repeats.
                    "depth": float(line["top"]) / height,
                }
            )
        return lines

    @staticmethod
    def _body_size(pages: List[List[Dict]]) -> float:
        """The size most of the document is set in — everything is relative to it."""
        weighted: Counter = Counter()
        for lines in pages:
            for line in lines:
                weighted[line["size"]] += len(line["text"])
        return weighted.most_common(1)[0][0] if weighted else 0.0

    def _heading_levels(
        self, pages: List[List[Dict]], body_size: float
    ) -> Dict[float, int]:
        """Map each above-body font size onto a heading level, largest first.

        Derived rather than configured: any PDF that sets its headings larger
        than its body text gets a hierarchy, without being told the sizes.
        """
        sizes = {
            line["size"]
            for lines in pages
            for line in lines
            if line["size"] > body_size
        }
        ranked = sorted(sizes, reverse=True)[: self.heading_levels]
        return {size: level for level, size in enumerate(ranked, start=1)}

    @staticmethod
    def _repeated(pages: List[List[Dict]]) -> set:
        """Running heads and footers: short lines repeating in the page margins.

        Position is the test, not repetition alone. "Efficacy" heads a section
        under most of the twenty-odd ingredients in this document, so repetition
        by itself would throw away the headings the chunker splits on; a running
        head is the line that repeats *and* sits in the top or bottom margin.
        """
        if len(pages) < 3:
            return set()
        seen: Counter = Counter()
        for lines in pages:
            margin = {
                line["text"]
                for line in lines
                if len(line["text"]) <= 60
                and not MARGIN_BAND < line["depth"] < 1.0 - MARGIN_BAND
            }
            for text in margin:
                seen[text] += 1
        threshold = max(3, int(len(pages) * 0.5))
        return {text for text, count in seen.items() if count >= threshold}

    def _render(
        self,
        lines: List[Dict],
        body_size: float,
        levels: Dict[float, int],
        boilerplate: set,
    ) -> List[str]:
        """One page's lines as markdown, paragraphs rejoined."""
        right_edge = max((line["x1"] for line in lines), default=0.0)
        out: List[str] = []
        paragraph: List[str] = []

        def flush() -> None:
            if paragraph:
                out.extend([" ".join(paragraph), ""])
                paragraph.clear()

        for line in lines:
            text = line["text"]
            if text in boilerplate or _is_page_number(text):
                continue

            level = levels.get(line["size"])
            # Bold is required only when the size alone is ambiguous — a size
            # shared with the body text is emphasis, not a heading.
            if level and (line["bold"] or line["size"] > body_size):
                flush()
                # A heading too wide for the column wraps onto the next line and
                # arrives as a second heading of the same level; join it back on
                # rather than splitting the document at a half-title.
                if out and out[-1] == "" and len(out) > 1 and _is_heading(out[-2], level):
                    out[-2] = f"{out[-2]} {text}"
                else:
                    out.extend([f"{'#' * level} {text}", ""])
                continue

            if text[:1] in BULLET_GLYPHS:
                flush()
                out.append(f"- {text[1:].strip()}")
                continue

            paragraph.append(text)
            # A line that stops short of the right margin ends its paragraph.
            if line["x1"] < right_edge - PARAGRAPH_SLACK:
                flush()
        flush()
        return out

    # -- cache -------------------------------------------------------------- #
    def _cache_path(self, source: Union[str, Path]) -> Path:
        stem = Path(str(source).rstrip("/")).stem or "source"
        slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:60]
        return self.cache_dir / f"{slug or 'source'}.md"


def _decode_glyphs(text: str) -> str:
    """Replace unmapped `(cid:N)` glyphs — the common ones are bullets."""
    return _CID.sub(lambda match: "•" if match.group(1) in {"127", "129"} else "", text)


def _is_heading(line: str, level: int) -> bool:
    return line.startswith("#" * level + " ") and not line.startswith("#" * (level + 1))


def _is_page_number(text: str) -> bool:
    """A standalone folio: "12", "- 12 -", "Page 12 of 32"."""
    stripped = text.strip(" -–—")
    if stripped.isdigit():
        return True
    return bool(re.fullmatch(r"(?i)page\s+\d+(\s+of\s+\d+)?", stripped))


def read_pages(text: str) -> Tuple[int, ...]:
    """Every page number marked in `text`, in order, without duplicates."""
    return tuple(dict.fromkeys(int(n) for n in PAGE_PATTERN.findall(text)))


def strip_pages(text: str) -> str:
    """Remove page markers, and the blank lines removing them leaves behind."""
    return re.sub(r"\n{3,}", "\n\n", PAGE_PATTERN.sub("", text)).strip()
