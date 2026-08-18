"""RAG Evaluation & Continuous Improvement Pipeline.

Scores retrieval and generation independently against clinical benchmarks,
auto-diagnoses root causes for low metrics, and generates actionable
engineering recommendations.

    python -m evaluation.cli run
    python -m evaluation.cli run --dataset path/to/golden.csv --threshold 0.7
"""

from .config import EvalSettings
from .dataset_loader import load_dataset
from .diagnostics import DiagnosticEngine
from .evaluate_rag import EvaluationEngine
from .report import ReportGenerator

__all__ = [
    "DiagnosticEngine",
    "EvalSettings",
    "EvaluationEngine",
    "ReportGenerator",
    "load_dataset",
]
