"""Grading the pipeline against a golden set of questions.

One module per step, the same shape as `rag`:

    dataset_loader  load_dataset       golden file -> [{question, ground_truth}]
    harness         collect            asks the live pipeline, keeps what it returns
    evaluate_rag    EvaluationEngine   four Ragas metrics over those records
    diagnostics     DiagnosticEngine   why a sample failed, and what to try
    report          ReportGenerator    JSON on disk, summary on the terminal

The point is that `harness` sits in the middle: the questions are fixed, the
answers are not, so the scores move when the pipeline changes. Configuration
lives in `rag.config.Settings` alongside everything else — the `eval_*` fields.

    python -m evaluation run

Scoring needs `ragas`, which is imported only when a run starts;
`evaluate_rag.available()` reports whether it is installed.
"""

from .dataset_loader import load_dataset
from .diagnostics import DiagnosticEngine
from .evaluate_rag import EvalResult, EvaluationEngine, SampleResult, available
from .harness import HarnessError, collect
from .report import ReportGenerator

__all__ = [
    "DiagnosticEngine",
    "EvalResult",
    "EvaluationEngine",
    "HarnessError",
    "ReportGenerator",
    "SampleResult",
    "available",
    "collect",
    "load_dataset",
]
