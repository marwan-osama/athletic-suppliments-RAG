"""A small, inspectable RAG pipeline over the NIH ODS athletic-supplements page.

One stage per module:

    fetching       SourceFetcher      HTML (file or URL) -> markdown
    preprocessing  MarkdownCleaner    markdown -> markdown without link/nav noise
    chunking       MarkdownChunker    markdown -> [Chunk], heading-aware
    augmentation   QuestionGenerator  [Chunk] -> hypothetical questions
    llm            LLMClient          the one place that calls the server
    embedding      ServerEmbedder     text -> vectors
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
from .embedding import HashEmbedder, ServerEmbedder
from .fetching import SourceFetcher
from .indexing import VectorIndex
from .llm import LLMClient, LLMError
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
    "LLMClient",
    "LLMError",
    "MarkdownChunker",
    "MarkdownCleaner",
    "QuestionGenerator",
    "RAGPipeline",
    "Retrieved",
    "Retriever",
    "ServerEmbedder",
    "Settings",
    "SourceFetcher",
    "Stage",
    "VectorIndex",
]
