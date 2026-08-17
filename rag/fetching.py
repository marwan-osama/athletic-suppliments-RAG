"""Stage 1 — turn an HTML source (local file or URL) into markdown."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

import trafilatura

from .schema import Stage


class SourceFetcher(Stage):
    """HTML in, markdown out, with a small on-disk cache.

    Accepts either a local `.html` file or a URL. Extraction is the slow part
    (and, for URLs, a network round trip), so the markdown is cached and reused
    unless `use_cache=False`.
    """

    def __init__(
        self,
        url: str | None = None,
        cache_dir: Union[str, Path] = ".cache",
        use_cache: bool = True,
        min_chars: int = 1_000,
    ):
        self.url = url  # lets relative links in a saved page resolve to absolute
        self.cache_dir = Path(cache_dir)
        self.use_cache = use_cache
        self.min_chars = min_chars

    def run(self, source: Union[str, Path]) -> str:
        cache_path = self._cache_path(source)
        if self.use_cache and cache_path.is_file():
            return cache_path.read_text(encoding="utf-8")

        markdown = trafilatura.extract(
            self._load(source),
            url=self.url or (str(source) if self._is_url(source) else None),
            output_format="markdown",
            include_tables=True,
            include_links=True,
            favor_recall=True,  # saved pages have odd wrappers; prune less
        )
        if not markdown or len(markdown) < self.min_chars:
            raise ValueError(
                f"Extraction produced {len(markdown or '')} chars from {source!r} "
                f"(expected at least {self.min_chars}) — content was lost."
            )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(markdown, encoding="utf-8")
        return markdown

    # -- internals ---------------------------------------------------------- #
    @staticmethod
    def _is_url(source: Union[str, Path]) -> bool:
        return str(source).startswith(("http://", "https://"))

    def _load(self, source: Union[str, Path]):
        if self._is_url(source):
            downloaded = trafilatura.fetch_url(str(source))
            if not downloaded:
                raise ValueError(f"Could not download {source}")
            return downloaded

        path = Path(source).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"No such HTML file: {path}")
        # Pass bytes so trafilatura detects the encoding itself.
        return path.read_bytes()

    def _cache_path(self, source: Union[str, Path]) -> Path:
        stem = Path(str(source).rstrip("/")).stem or "source"
        slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:60]
        return self.cache_dir / f"{slug or 'source'}.md"
