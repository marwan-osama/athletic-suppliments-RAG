"""Small helpers.

Retries and rate limiting used to live here; they now sit in `llm.py`,
next to the only code that makes requests.
"""

from __future__ import annotations

import re
from typing import Iterator, List, Optional, Sequence, TypeVar

T = TypeVar("T")

_LIST_MARKER = re.compile(r"^(?:[-*•]+\s*)?(?:\d+[.)]\s+)?")


def parse_lines(raw: str, limit: Optional[int] = None) -> List[str]:
    """One item per line, with bullets and numbering stripped.

    Shared by the two stages that ask the model for a list — hypothetical
    questions and query phrasings — because both get the same shape back.
    """
    lines = []
    for line in raw.splitlines():
        # Only leading list numbering — "100 mg of caffeine?" keeps its number.
        line = _LIST_MARKER.sub("", line.strip()).strip()
        if line:
            lines.append(line)
    return lines[:limit] if limit else lines


def batched(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield `items` in slices of `size`."""
    for start in range(0, len(items), max(1, size)):
        yield list(items[start : start + size])
