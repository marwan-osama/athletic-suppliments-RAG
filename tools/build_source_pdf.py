"""Typeset the ODS fact sheet into the PDF the pipeline indexes.

ODS publishes this fact sheet as a web page only — there is no official PDF to
download (every PDF linked from the page is a cited reference, not the fact
sheet). So the source document is produced here, from the same extraction the
pipeline used to read, and checked in under `data/`.

Headings are typeset at distinct point sizes because that is the only structural
signal a PDF carries: `PdfReader` recovers the heading hierarchy from font size,
the way it would for any other document.

    .venv/bin/python tools/build_source_pdf.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag.config import Settings              # noqa: E402
from rag.pipeline import cleaner_for         # noqa: E402
from rag.preprocessing import split_heading  # noqa: E402

SOURCE_MD = Path(".cache/dietary-supplements-for-exercise-and-athletic-performance-he.md")
OUTPUT = Path("data/ods-exercise-and-athletic-performance.pdf")

BODY_SIZE = 9.5
# Every heading level sits clearly above the body size, and clearly apart from
# its neighbours — this is what `PdfReader` reads the hierarchy back out of.
HEADING_SIZES = {1: 20.0, 2: 15.0, 3: 12.5, 4: 11.0}

_EMPHASIS = re.compile(r"\*{1,3}")
_TABLE_RULE = re.compile(r"^\|[\s|:-]*\|$")


def styles() -> dict:
    body = ParagraphStyle(
        "body", fontName="Helvetica", fontSize=BODY_SIZE, leading=BODY_SIZE * 1.45,
        spaceAfter=7, alignment=TA_JUSTIFY,
    )
    made = {"body": body}
    for level, size in HEADING_SIZES.items():
        made[f"h{level}"] = ParagraphStyle(
            f"h{level}", fontName="Helvetica-Bold", fontSize=size, leading=size * 1.25,
            spaceBefore=14 if level > 1 else 0, spaceAfter=6, keepWithNext=True,
        )
    return made


def escape(text: str) -> str:
    """Markdown emphasis out, XML entities in — reportlab parses its own markup."""
    text = _EMPHASIS.sub("", text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def table_row(line: str) -> str:
    """One markdown table row as a readable sentence."""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return " — ".join(cell for cell in cells if cell)


def flowables(markdown: str, style: dict) -> list:
    story, paragraph = [], []

    def flush() -> None:
        if paragraph:
            story.append(Paragraph(escape(" ".join(paragraph)), style["body"]))
            paragraph.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        level, title = split_heading(stripped)
        if level and title:
            flush()
            story.append(Paragraph(escape(title), style[f"h{min(level, 4)}"]))
        elif not stripped:
            flush()
        elif stripped.startswith("|"):
            flush()
            if not _TABLE_RULE.match(stripped):
                row = table_row(stripped)
                if row:
                    story.append(Paragraph(escape(row), style["body"]))
        elif stripped.startswith(("- ", "* ")):
            flush()
            story.append(Paragraph("• " + escape(stripped[2:]), style["body"]))
        else:
            paragraph.append(stripped)
    flush()
    story.append(Spacer(1, 2))
    return story


def stamp_page_number(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(LETTER[0] / 2, 0.55 * inch, str(canvas.getPageNumber()))
    canvas.restoreState()


def main() -> int:
    if not SOURCE_MD.is_file():
        # `.cache/` is gitignored, so a fresh clone has the built PDF but not the
        # extraction it came from. Regenerating needs the page fetched again.
        print(
            f"No extraction at {SOURCE_MD}.\n"
            "The built PDF is checked in at "
            f"{OUTPUT} — you only need this script to rebuild it, and that needs "
            "the ODS page extracted to the cache first.",
            file=sys.stderr,
        )
        return 1

    cleaned = cleaner_for(Settings())(SOURCE_MD.read_text(encoding="utf-8"))
    style = styles()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUTPUT), pagesize=LETTER,
        leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch,
        title="Dietary Supplements for Exercise and Athletic Performance",
        author="NIH Office of Dietary Supplements",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="page")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=stamp_page_number)])
    doc.build(flowables(cleaned, style))

    print(f"{OUTPUT} — {doc.page} pages, {OUTPUT.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
