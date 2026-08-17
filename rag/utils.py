"""Small helpers.

Retries and rate limiting used to live here; they now sit in `openrouter.py`,
next to the only code that makes requests.
"""

from __future__ import annotations

from typing import Iterator, List, Sequence, TypeVar

T = TypeVar("T")


def batched(items: Sequence[T], size: int) -> Iterator[List[T]]:
    """Yield `items` in slices of `size`."""
    for start in range(0, len(items), max(1, size)):
        yield list(items[start : start + size])
