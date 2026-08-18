"""A small, inspectable RAG pipeline over the NIH ODS athletic-supplements page.

One stage per module:

    fetching       SourceFetcher      HTML (file or URL) -> markdown
    preprocessing  MarkdownCleaner    markdown -> markdown without link/nav noise
    chunking       MarkdownChunker    markdown -> [Chunk], heading-aware
    augmentation   QuestionGenerator  [Chunk] -> hypothetical questions
    expansion      QueryExpander      query -> [query, other phrasings]
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
from .expansion import QueryExpander
from .fetching import SourceFetcher
from .indexing import VectorIndex
from .llm import LLMClient, LLMError
from .pipeline import RAGPipeline
from .preprocessing import MarkdownCleaner
from .retrieval import Retriever
from .schema import BuildReport, Chain, Chunk, Identity, Retrieved, Stage

__all__ = [
    "Answerer",
    "BuildReport",
    "Chain",
    "Chunk",
    "ChunkInspector",
    "ChunkReport",
    "HashEmbedder",
    "Identity",
    "LLMClient",
    "LLMError",
    "MarkdownChunker",
    "MarkdownCleaner",
    "QueryExpander",
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
