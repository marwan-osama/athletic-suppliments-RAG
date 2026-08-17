"""Chunk quality checks — the feedback loop for tuning size and overlap.

Bad chunks are the usual cause of bad retrieval, and they are visible before a
single embedding is paid for: fragments too small to carry meaning, chunks over
the requested size, leftover link soup, table rules with no prose.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Union

from .schema import Chunk

OVERSIZED, TINY, TABLE, LINK_HEAVY, NO_PROSE = (
    "OVERSIZED",
    "TINY",
    "TABLE",
    "LINK-HEAVY",
    "NO-PROSE",
)


@dataclass
class ChunkReport:
    total: int = 0
    min_chars: int = 0
    median_chars: float = 0.0
    max_chars: int = 0
    total_chars: int = 0
    sections: int = 0
    flags: Dict[int, List[str]] = field(default_factory=dict)

    def count(self, flag: str) -> int:
        return sum(flag in flags for flags in self.flags.values())

    @property
    def flagged(self) -> List[int]:
        return sorted(self.flags)

    def summary(self) -> str:
        return (
            f"{self.total} chunks across {self.sections} sections | "
            f"min {self.min_chars} | median {self.median_chars:.0f} | "
            f"max {self.max_chars} | total {self.total_chars:,} chars\n"
            f"oversized: {self.count(OVERSIZED)} | tiny: {self.count(TINY)} | "
            f"tables: {self.count(TABLE)} | link-heavy: {self.count(LINK_HEAVY)} | "
            f"no-prose: {self.count(NO_PROSE)}"
        )


class ChunkInspector:
    """`inspector(chunks)` -> `ChunkReport`."""

    def __init__(self, chunk_size: int = 600, tiny_below: int = 100):
        self.chunk_size = chunk_size
        self.tiny_below = tiny_below

    def flags_for(self, text: str) -> List[str]:
        flags = []
        if len(text) > self.chunk_size:
            flags.append(OVERSIZED)
        if len(text) < self.tiny_below:
            flags.append(TINY)
        if text.count("|") > 5:
            flags.append(TABLE)
        if text.count("](") > 4:
            flags.append(LINK_HEAVY)
        if not any(ch.isalpha() for ch in text):
            flags.append(NO_PROSE)
        return flags

    def __call__(self, chunks: Sequence[Chunk]) -> ChunkReport:
        if not chunks:
            return ChunkReport()

        sizes = [chunk.size for chunk in chunks]
        return ChunkReport(
            total=len(chunks),
            min_chars=min(sizes),
            median_chars=statistics.median(sizes),
            max_chars=max(sizes),
            total_chars=sum(sizes),
            sections=len({chunk.section for chunk in chunks}),
            flags={
                chunk.index: self.flags_for(chunk.text)
                for chunk in chunks
                if self.flags_for(chunk.text)
            },
        )

    def dump(self, chunks: Sequence[Chunk], path: Union[str, Path]) -> Path:
        """Write every chunk to a file, flags in the header — for eyeballing."""
        lines = ["# chunk dump\n"]
        for chunk in chunks:
            tag = " ".join(self.flags_for(chunk.text)) or "ok"
            lines.append(
                f"\n{'=' * 70}\n[{chunk.index:>4}] {chunk.size:>4} chars  {tag}"
                f"\nsection: {chunk.section or '-'}\n{'=' * 70}\n{chunk.text}\n"
            )
        out = Path(path)
        out.write_text("".join(lines), encoding="utf-8")
        return out
