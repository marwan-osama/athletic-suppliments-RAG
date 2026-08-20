"""Ask the pipeline every question in the golden set and keep what it returns.

This is the step that makes the scores mean something. The golden file supplies
the question and the reference answer; the contexts and the answer come from
`RAGPipeline.search()` and `RAGPipeline.answer()`, so a change to chunking,
top-k, query expansion or the prompt shows up in the next run's numbers.

Scoring a file that already contains its own contexts and answer would grade the
file instead, and would read the same however the pipeline was configured.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from rag.pipeline import RAGPipeline

# (done, total) — the UI draws a progress bar from this.
ProgressFn = Callable[[int, int], None]


class HarnessError(RuntimeError):
    """The pipeline cannot answer the golden set as configured."""


def check_ready(pipeline: RAGPipeline) -> None:
    """Fail early, with the fix, rather than scoring placeholder text.

    Both of these would otherwise produce a full set of confident-looking
    numbers describing nothing: an empty index retrieves no contexts, and an
    offline pipeline returns a notice string where the answer should be.
    """
    if pipeline.index.count == 0:
        raise HarnessError(
            f"The collection '{pipeline.settings.collection_name}' is empty — "
            "build the index before evaluating."
        )
    if pipeline.offline:
        raise HarnessError(
            "The model server is switched off, so there is nothing to grade: "
            "answers would be a placeholder notice. Turn it back on."
        )
    if not pipeline.can_answer:
        raise HarnessError(
            "Answer generation is switched off, so faithfulness and answer "
            "relevancy have no answer to score. Turn Answering on."
        )


def collect(
    pipeline: RAGPipeline,
    dataset: Sequence[Dict[str, Any]],
    on_progress: Optional[ProgressFn] = None,
) -> List[Dict[str, Any]]:
    """Run the pipeline over `dataset`, returning records ready for scoring.

    Each record keeps everything the golden file held and adds the two fields
    the metrics need: `contexts` (what retrieval returned) and `answer` (what
    generation made of them).
    """
    check_ready(pipeline)

    records: List[Dict[str, Any]] = []
    for done, row in enumerate(dataset, start=1):
        question = row["question"]
        hits = pipeline.search(question)
        records.append(
            {
                **row,
                "contexts": [hit.text for hit in hits],
                "answer": pipeline.answer(question, hits),
                # Kept for the report: which chunks were graded, and whether
                # query expansion had anything to do with the ranking.
                "retrieved": [
                    {
                        "chunk_id": hit.chunk_id,
                        "section": hit.section,
                        "pages": hit.pages_label,
                        "similarity": round(hit.similarity, 4),
                        "score": round(hit.score, 4),
                        "matches": hit.matches,
                        "match_type": hit.match_type,
                    }
                    for hit in hits
                ],
            }
        )
        if on_progress:
            on_progress(done, len(dataset))
    return records
