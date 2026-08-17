"""A small, inspectable RAG pipeline over the NIH ODS athletic-supplements page.

One stage per module:

    fetching       SourceFetcher      HTML (file or URL) -> markdown
    preprocessing  MarkdownCleaner    markdown -> markdown without link/nav noise
    chunking       MarkdownChunker    markdown -> [Chunk], heading-aware
    augmentation   QuestionGenerator  [Chunk] -> hypothetical questions
    openrouter     OpenRouterClient   the one place that calls the API
    embedding      OpenRouterEmbedder text -> vectors
    indexing       VectorIndex        chunks + questions -> ChromaDB
    retrieval      Retriever          query -> [Retrieved]
    answering      Answerer           query + chunks -> answer
    diagnostics    ChunkInspector     [Chunk] -> quality report

`RAGPipeline` in `pipeline.py` wires them together; stages also compose directly
with `|`.
"""

from .answering import Answerer
from .augmentation import QuestionGenerator
from .chunking import MarkdownChunker
from .config import Settings
from .diagnostics import ChunkInspector, ChunkReport
from .embedding import HashEmbedder, OpenRouterEmbedder
from .fetching import SourceFetcher
from .indexing import VectorIndex
from .openrouter import OpenRouterClient, OpenRouterError
from .pipeline import RAGPipeline
from .preprocessing import MarkdownCleaner
from .retrieval import Retriever
from .schema import BuildReport, Chain, Chunk, Retrieved, Stage

__all__ = [
    "Answerer",
    "BuildReport",
    "Chain",
    "Chunk",
    "ChunkInspector",
    "ChunkReport",
    "HashEmbedder",
    "MarkdownChunker",
    "MarkdownCleaner",
    "OpenRouterClient",
    "OpenRouterEmbedder",
    "OpenRouterError",
    "QuestionGenerator",
    "RAGPipeline",
    "Retrieved",
    "Retriever",
    "Settings",
    "SourceFetcher",
    "Stage",
    "VectorIndex",
]
