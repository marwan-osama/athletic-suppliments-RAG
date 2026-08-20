"""The pipeline: wires the stages together and exposes build / search / answer.

    read PDF -> clean -> chunk -> (questions) -> embed -> index
                        query -> (expand) -> retrieve -> (rerank) -> answer

Stages compose with `|`, so `pipeline.chunk()` is literally
`(fetcher | cleaner | chunker)(source)`.

Every stage takes its hyperparameters from `Settings`, and the optional ones —
cleaning, question generation, query expansion, answering, the fetch cache, the
model server itself — drop out when their switch is off. Settings that change the stored
vectors are baked into `Settings.index_key`; the rest can be pushed onto a live
pipeline with `apply()`, which is what lets the UI move a slider without
reopening the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

from .answering import Answerer
from .augmentation import QuestionGenerator
from .chunking import MarkdownChunker
from .config import Settings
from .diagnostics import ChunkInspector, ChunkReport
from .embedding import HashEmbedder, ServerEmbedder
from .expansion import QueryExpander
from .fetching import PdfReader
from .indexing import VectorIndex
from .llm import LLMClient
from .preprocessing import MarkdownCleaner
from .reranking import Reranker
from .retrieval import Retriever
from .schema import BuildReport, Chain, Chunk, Identity, Retrieved, Stage

# (stage label, done, total) — one callback covers every long-running step.
StageProgress = Callable[[str, int, int], None]

# Measured through LM Studio on this machine: gpt-oss-20b answers this prompt in
# ~1s (it spends about 9 tokens reasoning), which comes to ~0.9s per chunk with
# the default 8 workers. Embeddings are cheaper still: 288 chunks in 8s.
# Both are model-specific — re-measure after swapping either one.
SECONDS_PER_GENERATION = 0.9
SECONDS_PER_EMBED_CALL = 0.4

OFFLINE_NOTICE = "Running offline — turn the model server back on to generate answers."
DISABLED_NOTICE = "Answer generation is switched off — turn it on to compose one."


@dataclass
class BuildEstimate:
    embedding_calls: int
    generation_calls: int
    minutes: float


def _step(label: str, on_progress: StageProgress | None):
    """Bind a stage label so inner stages can report plain (done, total)."""
    if on_progress is None:
        return None
    return lambda done, total: on_progress(label, done, total)


def cleaner_for(settings: Settings) -> Stage:
    """The cleaning stage, or a pass-through when it is switched off."""
    if not settings.enable_cleaning:
        return Identity()
    return MarkdownCleaner(
        strip_links=settings.strip_links,
        strip_citations=settings.strip_citations,
        drop_boilerplate=settings.drop_boilerplate,
        name_empty_headings=settings.name_empty_headings,
        drop_sections=settings.drop_sections,
    )


def reader(settings: Settings) -> Chain:
    """The free half of the pipeline: read | clean | chunk.

    Built on its own so the UI can re-chunk on every slider move without opening
    a database or a connection to the model server.
    """
    return (
        PdfReader(
            cache_dir=settings.cache_dir,
            use_cache=settings.use_cache,
            min_chars=settings.fetch_min_chars,
            heading_levels=settings.pdf_heading_levels,
            drop_repeated_lines=settings.pdf_drop_repeated_lines,
        )
        | cleaner_for(settings)
        | MarkdownChunker(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            min_chars=settings.min_chunk_chars,
            prepend_section=settings.prepend_section,
            max_section_chars=settings.max_section_chars,
        )
    )


class RAGPipeline:
    def __init__(self, settings: Settings, log: Callable[[str], None] = print):
        self.settings = settings
        self.log = log
        self.client: Optional[LLMClient] = (
            LLMClient(
                base_url=settings.base_url,
                api_key=settings.api_key,
                requests_per_minute=settings.requests_per_minute,
                timeout=settings.request_timeout,
                max_retries=settings.max_retries,
                extra_body=settings.extra_body(),
                log=log,
            )
            if settings.use_server
            else None
        )
        # A second client only when embeddings live somewhere else — otherwise
        # this is the generation client, so the rate limiter stays shared and
        # one endpoint is still paced as one endpoint.
        embed_base_url, embed_key = settings.embed_endpoint()
        self.embed_client: Optional[LLMClient] = (
            self.client
            if not self.client or embed_base_url == settings.base_url
            else LLMClient(
                base_url=embed_base_url,
                api_key=embed_key,
                requests_per_minute=settings.requests_per_minute,
                timeout=settings.request_timeout,
                max_retries=settings.max_retries,
                log=log,
            )
        )

        self.reader = reader(settings)
        self.fetcher, self.cleaner, self.chunker = self.reader.stages
        self.inspector = ChunkInspector(
            chunk_size=settings.chunk_size, tiny_below=settings.tiny_below
        )

        self.embedder = (
            ServerEmbedder(
                self.embed_client,
                model_name=settings.embed_model,
                batch_size=settings.embed_batch_size,
                document_prefix=settings.document_prefix,
                query_prefix=settings.query_prefix,
                dimensions=settings.embed_dimensions,
            )
            if self.client
            else HashEmbedder()
        )
        self.index = VectorIndex(
            self.embedder,
            db_path=settings.db_path,
            collection_name=settings.collection_name,
        )
        # The expander exists whenever a server does; `num_expansions` is what
        # switches it off, so `apply()` can toggle it without a rebuild.
        self.expander = QueryExpander(self.client, log=log) if self.client else None
        # Same shape as the expander: it exists whenever a server does, and
        # `rerank_candidates` is what switches it off, so `apply()` can toggle it.
        self.reranker = Reranker(self.client, log=log) if self.client else None
        self.retriever = Retriever(
            self.index, expander=self.expander, reranker=self.reranker
        )
        self.generator = (
            QuestionGenerator(self.client, log=log)
            if self.client and settings.questions_per_chunk > 0
            else None
        )
        self.answerer = Answerer(self.client, log=log) if self.client else None

        # One code path sets every tunable field, so a stage cannot end up
        # configured one way at construction and another way after a slider move.
        self.apply(settings)

    @classmethod
    def from_env(cls, **overrides) -> "RAGPipeline":
        return cls(Settings.from_env(**overrides))

    def apply(self, settings: Settings) -> None:
        """Push the runtime-tunable settings onto the stages already built.

        Everything here can change without invalidating the index, which is why
        the UI can move these controls without a rebuild. Anything that *does*
        change the stored vectors is part of `Settings.index_key`, and changing
        one of those gets you a different pipeline (and its own collection)
        instead of a silently mismatched index.
        """
        self.settings = settings

        self.fetcher.use_cache = settings.use_cache
        self.fetcher.min_chars = settings.fetch_min_chars
        self.inspector.tiny_below = settings.tiny_below

        self.retriever.top_k = settings.top_k
        self.retriever.dedupe = settings.dedupe_by_chunk
        self.retriever.overfetch = settings.retrieval_overfetch
        self.retriever.match_boost = settings.match_boost
        self.retriever.match_boost_cap = settings.match_boost_cap
        self.retriever.rerank_candidates = settings.rerank_candidates

        if self.client is not None:
            self.client.tune(
                requests_per_minute=settings.requests_per_minute,
                timeout=settings.request_timeout,
                max_retries=settings.max_retries,
            )
        if isinstance(self.embedder, ServerEmbedder):
            self.embedder.batch_size = settings.embed_batch_size
        if self.generator is not None:
            self.generator.model_name = settings.llm_model
            self.generator.num_questions = settings.questions_per_chunk
            self.generator.workers = settings.question_workers
            self.generator.temperature = settings.question_temperature
            self.generator.max_tokens = settings.question_max_tokens
            self.generator.reasoning_effort = settings.reasoning_effort
        if self.expander is not None:
            self.expander.model_name = settings.llm_model
            self.expander.num_expansions = settings.query_expansions
            self.expander.temperature = settings.query_expansion_temperature
            self.expander.max_tokens = settings.query_expansion_max_tokens
            self.expander.reasoning_effort = settings.reasoning_effort
        if self.reranker is not None:
            self.reranker.model_name = settings.llm_model
            self.reranker.temperature = settings.rerank_temperature
            self.reranker.max_tokens = settings.rerank_max_tokens
            self.reranker.snippet_chars = settings.rerank_snippet_chars
            self.reranker.reasoning_effort = settings.reasoning_effort
        if self.answerer is not None:
            self.answerer.model_name = settings.llm_model
            self.answerer.temperature = settings.answer_temperature
            self.answerer.max_tokens = settings.answer_max_tokens
            self.answerer.max_context_chars = settings.answer_max_context_chars
            self.answerer.reasoning_effort = settings.reasoning_effort

    @property
    def offline(self) -> bool:
        """True when the model server is switched off (hash vectors, no LLM)."""
        return self.client is None

    @property
    def can_expand(self) -> bool:
        """Whether searches will be expanded: needs a server and a non-zero count."""
        return self.expander is not None and self.settings.query_expansions > 0

    @property
    def can_rerank(self) -> bool:
        """Whether searches will be reranked: needs a server and a candidate pool."""
        return self.reranker is not None and self.settings.rerank_candidates > 0

    @property
    def can_answer(self) -> bool:
        """Whether the Answer step is available: needs a server and its switch."""
        return self.answerer is not None and self.settings.enable_answers

    def estimate_build(self, chunk_count: int) -> "BuildEstimate":
        """What a build of `chunk_count` chunks would cost in calls and minutes.

        Generation dominates by a wide margin: one call per chunk, and the local
        model spends most of each call reasoning before it answers.
        """
        rows = chunk_count * (1 + self.settings.questions_per_chunk)
        embedding_calls = -(-rows // self.settings.embed_batch_size)  # ceil
        question_calls = chunk_count if self.settings.questions_per_chunk else 0
        seconds = (
            embedding_calls * SECONDS_PER_EMBED_CALL
            + question_calls * SECONDS_PER_GENERATION
        )
        return BuildEstimate(embedding_calls, question_calls, seconds / 60)

    # -- reading the source (no API calls, no cost) -------------------------- #
    def chunk(self, source: Optional[str] = None) -> List[Chunk]:
        return self.reader(source or self.settings.source)

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
            chunks,
            questions,
            batch_size=self.settings.index_batch_size,
            on_progress=_step("indexing", on_progress),
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
            return OFFLINE_NOTICE
        if not self.settings.enable_answers:
            return DISABLED_NOTICE
        return self.answerer(query, chunks)
