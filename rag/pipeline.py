"""The pipeline: wires the stages together and exposes build / search / answer.

    fetch -> clean -> chunk -> (questions) -> embed -> index -> retrieve -> answer

Stages compose with `|`, so `pipeline.chunk()` is literally
`(fetcher | cleaner | chunker)(source)`.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from .answering import Answerer
from .augmentation import QuestionGenerator
from .chunking import MarkdownChunker
from .config import Settings
from .diagnostics import ChunkInspector, ChunkReport
from .embedding import HashEmbedder, OpenRouterEmbedder
from .fetching import SourceFetcher
from .indexing import VectorIndex
from .openrouter import OpenRouterClient
from .preprocessing import MarkdownCleaner
from .retrieval import Retriever
from .schema import BuildReport, Chunk, Retrieved

# (stage label, done, total) — one callback covers every long-running step.
StageProgress = Callable[[str, int, int], None]


def _step(label: str, on_progress: StageProgress | None):
    """Bind a stage label so inner stages can report plain (done, total)."""
    if on_progress is None:
        return None
    return lambda done, total: on_progress(label, done, total)


class RAGPipeline:
    def __init__(self, settings: Settings, log: Callable[[str], None] = print):
        self.settings = settings
        self.log = log
        self.client: Optional[OpenRouterClient] = (
            OpenRouterClient(
                settings.api_key,
                base_url=settings.base_url,
                requests_per_minute=settings.requests_per_minute,
                log=log,
            )
            if settings.has_api_key
            else None
        )

        self.fetcher = SourceFetcher(
            url=settings.source_url, cache_dir=settings.cache_dir
        )
        self.cleaner = MarkdownCleaner()
        self.chunker = MarkdownChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            min_chars=settings.min_chunk_chars,
            prepend_section=settings.prepend_section,
        )
        self.inspector = ChunkInspector(chunk_size=settings.chunk_size)

        self.embedder = (
            OpenRouterEmbedder(
                self.client,
                model_name=settings.embed_model,
                batch_size=settings.embed_batch_size,
                document_prefix=settings.document_prefix,
                query_prefix=settings.query_prefix,
            )
            if self.client
            else HashEmbedder()
        )
        self.index = VectorIndex(
            self.embedder,
            db_path=settings.db_path,
            collection_name=settings.collection_name,
        )
        self.retriever = Retriever(
            self.index, top_k=settings.top_k, dedupe=settings.dedupe_by_chunk
        )
        self.generator = (
            QuestionGenerator(
                self.client,
                model_name=settings.llm_model,
                num_questions=settings.questions_per_chunk,
                workers=settings.question_workers,
                log=log,
            )
            if self.client and settings.questions_per_chunk > 0
            else None
        )
        self.answerer = (
            Answerer(self.client, model_name=settings.llm_model, log=log)
            if self.client
            else None
        )

    @classmethod
    def from_env(cls, **overrides) -> "RAGPipeline":
        return cls(Settings.from_env(**overrides))

    @property
    def offline(self) -> bool:
        """True when running without an API key (hash embeddings, no LLM)."""
        return self.client is None

    def requests_for_build(self, chunk_count: int) -> int:
        """How many OpenRouter calls a build of `chunk_count` chunks would make.

        Worth knowing before starting: free models are paced, so this count times
        `60 / requests_per_minute` is roughly how long the build will take.
        """
        rows = chunk_count * (1 + self.settings.questions_per_chunk)
        embedding_calls = -(-rows // self.settings.embed_batch_size)  # ceil
        question_calls = chunk_count if self.settings.questions_per_chunk else 0
        return embedding_calls + question_calls

    # -- reading the source (no API calls, no cost) -------------------------- #
    def chunk(self, source: Optional[str] = None) -> List[Chunk]:
        pipeline = self.fetcher | self.cleaner | self.chunker
        return pipeline(source or self.settings.source)

    def inspect(self, chunks: List[Chunk]) -> ChunkReport:
        return self.inspector(chunks)

    # -- indexing ------------------------------------------------------------ #
    def build(
        self,
        source: Optional[str] = None,
        force: bool = False,
        on_progress: StageProgress | None = None,
    ) -> BuildReport:
        """Chunk the source and index it. Existing collections are left alone
        unless `force=True`, which rebuilds from scratch."""
        collection = self.settings.collection_name

        if self.index.count and not force:
            return BuildReport(
                collection=collection, rows_indexed=self.index.count, skipped=True
            )
        if force and self.index.count:
            self.index.reset()

        chunks = self.chunk(source)
        if on_progress:
            on_progress("chunking", len(chunks), len(chunks))

        questions = (
            self.generator.run(chunks, on_progress=_step("questions", on_progress))
            if self.generator
            else {}
        )
        rows = self.index.add(
            chunks, questions, on_progress=_step("indexing", on_progress)
        )

        return BuildReport(
            collection=collection,
            chunks=chunks,
            questions=questions,
            rows_indexed=rows,
        )

    # -- querying ------------------------------------------------------------ #
    def search(self, query: str, top_k: Optional[int] = None) -> List[Retrieved]:
        return self.retriever.run(query, top_k=top_k)

    def answer(self, query: str, chunks: List[Retrieved]) -> str:
        if self.answerer is None:
            return "No API key configured — set OPENROUTER_API_KEY to generate answers."
        return self.answerer(query, chunks)
