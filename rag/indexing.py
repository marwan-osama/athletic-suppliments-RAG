"""Stage 6 — the vector store: writes chunks (and their questions) to ChromaDB.

Chroma metadata values must be scalars, so a chunk's page tuple is stored as a
comma-separated string and parsed back by `Retriever`. Question rows repeat their
parent's pages: a question hit resolves to the parent chunk, and it has to cite
the same page the chunk would.

Question rows store only a pointer to their parent chunk, not a copy of its
text; `texts_for()` resolves the pointers at query time. One copy of the
document, and edits to a chunk cannot leave a stale duplicate behind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

import chromadb

from .schema import Chunk, ProgressFn, report

CHUNK_ROW = "chunk"
QUESTION_ROW = "question"


def pages_to_metadata(pages: Iterable[int]) -> str:
    """`(7, 8)` -> `"7,8"` — Chroma stores scalars, not sequences."""
    return ",".join(str(page) for page in pages)


def pages_from_metadata(raw: Any) -> tuple:
    """`"7,8"` -> `(7, 8)`, tolerating rows written before pages existed."""
    if not raw:
        return ()
    return tuple(
        int(part) for part in str(raw).split(",") if part.strip().isdigit()
    )


class VectorIndex:
    """Thin, typed wrapper over one persistent Chroma collection."""

    def __init__(
        self,
        embedder,
        db_path: Union[str, Path] = "./chroma_db",
        collection_name: str = "ods_health_facts",
    ):
        self.embedder = embedder
        self.db_path = str(db_path)
        self.collection_name = collection_name
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedder,
            metadata={"hnsw:space": "cosine"},
        )

    # -- writing ------------------------------------------------------------ #
    def add(
        self,
        chunks: Sequence[Chunk],
        questions: Optional[Dict[str, List[str]]] = None,
        batch_size: int = 100,
        on_progress: ProgressFn | None = None,
    ) -> int:
        """Upsert chunks plus any generated questions. Returns rows written."""
        ids, documents, metadatas = [], [], []

        for chunk in chunks:
            ids.append(chunk.id)
            documents.append(chunk.text)
            metadatas.append(
                {
                    "type": CHUNK_ROW,
                    "parent_id": chunk.id,
                    "chunk_index": chunk.index,
                    "section": chunk.section,
                    "pages": pages_to_metadata(chunk.pages),
                }
            )
            for position, question in enumerate((questions or {}).get(chunk.id, [])):
                ids.append(f"{chunk.id}-q{position}")
                documents.append(question)
                metadatas.append(
                    {
                        "type": QUESTION_ROW,
                        "parent_id": chunk.id,
                        "chunk_index": chunk.index,
                        "section": chunk.section,
                        "pages": pages_to_metadata(chunk.pages),
                    }
                )

        # Upsert in slices so the embedding API isn't handed one huge request.
        for start in range(0, len(ids), batch_size):
            stop = start + batch_size
            self.collection.upsert(
                ids=ids[start:stop],
                documents=documents[start:stop],
                metadatas=metadatas[start:stop],
            )
            report(on_progress, min(stop, len(ids)), len(ids))
        return len(ids)

    def reset(self) -> None:
        """Drop the collection and recreate it empty."""
        self.client.delete_collection(self.collection_name)
        self.collection = self._open()

    # -- reading ------------------------------------------------------------ #
    @property
    def count(self) -> int:
        return self.collection.count()

    def query(self, vector: List[float], n_results: int) -> Dict[str, Any]:
        return self.collection.query(
            query_embeddings=[vector],
            n_results=max(1, n_results),
            include=["documents", "metadatas", "distances"],
        )

    def texts_for(self, chunk_ids: Iterable[str]) -> Dict[str, str]:
        """Resolve chunk ids to their text in one round trip."""
        chunk_ids = list(dict.fromkeys(chunk_ids))
        if not chunk_ids:
            return {}
        rows = self.collection.get(ids=chunk_ids, include=["documents"])
        return dict(zip(rows["ids"], rows["documents"]))

    def collections(self) -> List[str]:
        return sorted(c.name for c in self.client.list_collections())

    def stats(self) -> Dict[str, int]:
        """Row counts per type — cheap sanity check that indexing worked."""
        counts = {CHUNK_ROW: 0, QUESTION_ROW: 0}
        rows = self.collection.get(include=["metadatas"])
        for metadata in rows["metadatas"] or []:
            row_type = metadata.get("type", CHUNK_ROW)
            counts[row_type] = counts.get(row_type, 0) + 1
        return counts
