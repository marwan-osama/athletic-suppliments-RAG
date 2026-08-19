"""Command line entry point: `python -m evaluation <command>`.

    python -m evaluation run
    python -m evaluation run --dataset path/to/golden.csv --threshold 0.7
    python -m evaluation run --no-llm-diagnostics
    python -m evaluation run --eval-model gpt-4o --eval-base-url https://api.openai.com/v1

Every run asks the live pipeline each question in the golden set and grades what
comes back, so the index has to be built first (`python -m rag.cli build`).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from rag.config import Settings
from rag.pipeline import RAGPipeline

from .dataset_loader import load_dataset
from .diagnostics import DiagnosticEngine
from .evaluate_rag import EvaluationEngine, EvaluationUnavailable
from .harness import HarnessError, collect
from .report import ReportGenerator

# Overrides that map straight onto a `Settings` field.
OVERRIDES = {
    "dataset": "eval_dataset_path",
    "threshold": "eval_threshold",
    "output": "eval_output_dir",
    "eval_model": "eval_llm_model",
    "eval_base_url": "eval_base_url",
    "top_k": "top_k",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluation", description="Grade the pipeline against a golden set"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="run the pipeline and score what it returns")
    run.add_argument("--dataset", type=Path, help=".json, .jsonl or .csv golden set")
    run.add_argument("--threshold", type=float, help="a metric below this fails (0.8)")
    run.add_argument("--output", type=Path, help="where reports are written")
    run.add_argument("--eval-model", help="judge model (default: the pipeline's own)")
    run.add_argument("--eval-base-url", help="judge endpoint, for a hosted judge")
    run.add_argument("--top-k", type=int, help="retrieval depth to evaluate at")
    run.add_argument(
        "--no-llm-diagnostics", action="store_true",
        help="rule-based diagnosis only — skips a generation call per failure",
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    values = vars(args)
    overrides = {
        field: values[name]
        for name, field in OVERRIDES.items()
        if values.get(name) is not None
    }
    if args.no_llm_diagnostics:
        overrides["eval_llm_diagnostics"] = False
    return Settings.from_env(**overrides)


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)
    pipeline = RAGPipeline(settings)
    base_url, model, embed_model = settings.eval_endpoint()

    print(f"Collection : {settings.collection_name} ({pipeline.index.count:,} rows)")
    print(f"Judge      : {model} · {embed_model} @ {base_url}")
    print(f"Dataset    : {settings.eval_dataset_path}")
    print(f"Threshold  : {settings.eval_threshold}\n")

    dataset = load_dataset(settings.eval_dataset_path)
    print(f"Asking the pipeline {len(dataset)} questions...")

    def progress(done: int, total: int) -> None:
        print(f"  {done}/{total}")

    try:
        records = collect(pipeline, dataset, on_progress=progress)
    except HarnessError as exc:
        print(f"\nCannot evaluate: {exc}", file=sys.stderr)
        return 1

    print("\nScoring (a few minutes — the judge reads every sample)...")
    try:
        result = EvaluationEngine(settings).run(records)
    except EvaluationUnavailable as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    diagnostics = DiagnosticEngine(settings).run(result)
    print(f"  {diagnostics.total_failures} failing samples diagnosed.\n")

    reporter = ReportGenerator(settings.eval_output_dir)
    print(f"Report: {reporter.save_json(result, diagnostics, settings)}\n")
    reporter.print_cli_summary(result, diagnostics)
    return 0 if result.passing else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
