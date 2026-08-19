"""Offline tests for the evaluation package — no server, no ragas needed.

    python tests/test_evaluation.py     (or: pytest tests)

Scoring itself is Ragas' job and needs a model to judge with, so what is tested
here is everything around it: that the harness asks the real pipeline, that it
refuses to grade a run that would be meaningless, and that the loader and the
acronym expansion behave.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from evaluation.dataset_loader import DatasetLoadError, load_dataset
from evaluation.evaluate_rag import (
    METRIC_NAMES,
    METRIC_STAGE,
    EvalResult,
    SampleResult,
    _as_score,
    normalize_medical_text,
)
from evaluation.harness import HarnessError, check_ready, collect
from rag.config import Settings
from rag.schema import Retrieved


class FakePipeline:
    """Stands in for `RAGPipeline` — records what it was asked."""

    def __init__(self, rows: int = 10, offline: bool = False, can_answer: bool = True):
        self.index = type("Index", (), {"count": rows})()
        self.offline = offline
        self.can_answer = can_answer
        self.settings = Settings()
        self.asked: list[str] = []

    def search(self, question, top_k=None):
        self.asked.append(question)
        return [
            Retrieved(
                chunk_id="c0001-aaaa", text=f"passage about {question}",
                similarity=0.7, match_type="chunk", section="Creatine > Efficacy",
                chunk_index=1, matches=2, boost=0.05,
            )
        ]

    def answer(self, question, hits):
        return f"answer to {question}"


def test_harness_asks_the_pipeline_rather_than_reading_the_file():
    """The whole point: contexts and answers come from the live pipeline.

    A golden file carrying its own contexts and answer must not be able to
    supply them, or the scores would describe the file and read the same
    however the pipeline is configured.
    """
    pipeline = FakePipeline()
    dataset = [
        {
            "question": "does creatine help sprinting?",
            "ground_truth": "yes, via phosphocreatine",
            # Both of these are stale leftovers and must be overwritten.
            "contexts": ["a context the file made up"],
            "answer": "an answer the file made up",
        }
    ]

    records = collect(pipeline, dataset)

    assert pipeline.asked == ["does creatine help sprinting?"]
    assert records[0]["answer"] == "answer to does creatine help sprinting?"
    assert records[0]["contexts"] == ["passage about does creatine help sprinting?"]
    assert "made up" not in json.dumps(records), "the file's own text survived"
    # The reference answer is the one thing the file is allowed to supply.
    assert records[0]["ground_truth"] == "yes, via phosphocreatine"


def test_harness_records_what_retrieval_did():
    records = collect(FakePipeline(), [{"question": "q", "ground_truth": "g"}])
    retrieved = records[0]["retrieved"][0]

    assert retrieved["chunk_id"] == "c0001-aaaa"
    assert retrieved["similarity"] == 0.7
    assert retrieved["matches"] == 2, "query-expansion agreement is kept"
    assert retrieved["score"] == 0.75, "the boosted rank is kept beside it"


def test_harness_reports_progress():
    seen = []
    dataset = [{"question": f"q{n}", "ground_truth": "g"} for n in range(3)]
    collect(FakePipeline(), dataset, on_progress=lambda d, t: seen.append((d, t)))
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_harness_refuses_a_run_that_would_grade_nothing():
    """Every one of these would still produce a full set of numbers."""
    try:
        check_ready(FakePipeline(rows=0))
    except HarnessError as error:
        assert "empty" in str(error) and "build" in str(error).lower(), error
    else:
        raise AssertionError("an empty index must not be evaluated")

    try:
        check_ready(FakePipeline(offline=True, can_answer=False))
    except HarnessError as error:
        assert "server" in str(error).lower(), error
    else:
        raise AssertionError("an offline pipeline answers with a notice, not an answer")

    try:
        check_ready(FakePipeline(can_answer=False))
    except HarnessError as error:
        assert "Answering" in str(error), error
    else:
        raise AssertionError("no answer means faithfulness has nothing to score")

    check_ready(FakePipeline())  # a ready pipeline raises nothing


def test_dataset_needs_only_the_golden_half():
    """contexts and answer are outputs now, so a file need not carry them."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "golden.json"
        path.write_text(
            json.dumps([{"question": "q", "ground_truth": "g"}]), encoding="utf-8"
        )
        assert load_dataset(path) == [{"question": "q", "ground_truth": "g"}]

        path.write_text(json.dumps([{"question": "q"}]), encoding="utf-8")
        try:
            load_dataset(path)
        except DatasetLoadError as error:
            assert "ground_truth" in str(error), error
        else:
            raise AssertionError("a missing reference answer must be reported")


def test_dataset_ships_questions_and_references_only():
    """The golden file in the repo must not carry pre-baked outputs."""
    rows = load_dataset(Settings().eval_dataset_path)
    assert rows, "the shipped golden set is empty"
    for row in rows:
        assert set(row) == {"question", "ground_truth"}, sorted(row)


def test_acronyms_expand_longest_first():
    expanded = normalize_medical_text("BCAAs and HMB raise ATP")
    assert "BCAAs (branched-chain amino acids)" in expanded, expanded
    assert "HMB (beta-hydroxy beta-methylbutyrate)" in expanded
    # A word that merely contains an acronym is left alone.
    assert normalize_medical_text("GIANT") == "GIANT"


def test_a_metric_ragas_could_not_compute_scores_zero():
    assert _as_score(0.75) == 0.75
    assert _as_score(None) == 0.0
    assert _as_score(float("nan")) == 0.0, "NaN would poison the aggregate"


def test_failing_metrics_name_the_stage_to_look_at():
    sample = SampleResult(
        question="q", ground_truth="g", answer="a", contexts=[],
        scores={"context_recall": 0.4, "faithfulness": 0.3},
        failure_flags=["context_recall", "faithfulness"],
    )
    assert sample.failing_stages == ["retrieval", "answering"]
    assert set(METRIC_STAGE) == set(METRIC_NAMES), "every metric names a stage"

    result = EvalResult(samples=[sample], aggregate={"context_recall": 0.9}, threshold=0.8)
    assert result.passing is True
    assert EvalResult(aggregate={"faithfulness": 0.5}, threshold=0.8).passing is False


def test_the_judge_inherits_the_pipeline_endpoint_until_told_otherwise():
    settings = Settings()
    assert settings.eval_endpoint() == (
        settings.base_url, settings.llm_model, settings.embed_model
    )
    judged = settings.with_(eval_llm_model="gpt-4o", eval_base_url="https://api/v1")
    assert judged.eval_endpoint() == (
        "https://api/v1", "gpt-4o", settings.embed_model
    )


def test_evaluation_settings_never_touch_the_index():
    """Grading reads the index; it must not be able to fork or rebuild it."""
    settings = Settings()
    for field, value in [
        ("eval_threshold", 0.5), ("eval_llm_model", "gpt-4o"),
        ("eval_max_workers", 8), ("eval_normalize_acronyms", False),
    ]:
        changed = settings.with_(**{field: value})
        assert changed.index_key == settings.index_key, field
        assert changed.collection_name == settings.collection_name, field
        assert changed.reader_key == settings.reader_key, field


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'all tests passed' if not failures else f'{failures} failure(s)'}")
    sys.exit(1 if failures else 0)
