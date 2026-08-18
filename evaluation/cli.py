"""CLI entry point for the evaluation pipeline.

Usage::

    python -m evaluation.cli run
    python -m evaluation.cli run --dataset path/to/golden.csv --threshold 0.7
    python -m evaluation.cli run --no-llm-diagnostics   # skip LLM analysis
    python -m evaluation.cli run --base-url https://api.openai.com/v1 --model gpt-4o
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from .config import EvalSettings
from .dataset_loader import load_dataset
from .diagnostics import DiagnosticEngine
from .evaluate_rag import EvaluationEngine
from .report import ReportGenerator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evaluation",
        description="RAG Evaluation & Continuous Improvement Pipeline",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run_cmd = commands.add_parser(
        "run", help="Run the full evaluation pipeline on a golden dataset"
    )
    run_cmd.add_argument(
        "--dataset",
        type=Path,
        help="Path to golden dataset (.json, .jsonl, or .csv). "
        "Default: evaluation/data/golden_dataset.json",
    )
    run_cmd.add_argument(
        "--threshold",
        type=float,
        default=None,
        help="Acceptance threshold for all metrics (default: 0.8)",
    )
    run_cmd.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Directory for JSON reports (default: ./eval_results)",
    )
    run_cmd.add_argument(
        "--model",
        default=None,
        help="Override evaluator LLM model name",
    )
    run_cmd.add_argument(
        "--base-url",
        default=None,
        help="Override evaluator LLM base URL",
    )
    run_cmd.add_argument(
        "--api-key",
        default=None,
        help="API key for the evaluator LLM (if using a hosted endpoint)",
    )
    run_cmd.add_argument(
        "--no-llm-diagnostics",
        action="store_true",
        help="Skip LLM-powered diagnostic analysis (rule-based only)",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command != "run":
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    # ── build settings ───────────────────────────────────────────────── #
    overrides = {}
    if args.dataset:
        overrides["dataset_path"] = args.dataset
    if args.threshold is not None:
        overrides["threshold"] = args.threshold
    if args.output:
        overrides["output_dir"] = args.output
    if args.model:
        overrides["eval_llm_model"] = args.model
    if args.base_url:
        overrides["eval_llm_base_url"] = args.base_url
    if args.api_key:
        overrides["eval_llm_api_key"] = args.api_key

    settings = EvalSettings.from_env(**overrides)

    print(f"Evaluator LLM : {settings.eval_llm_model}")
    print(f"Base URL      : {settings.eval_llm_base_url}")
    print(f"Dataset       : {settings.dataset_path}")
    print(f"Threshold     : {settings.threshold}")
    print(f"Output        : {settings.output_dir}")
    print()

    # ── 1. load dataset ──────────────────────────────────────────────── #
    print("Loading golden dataset...")
    dataset = load_dataset(settings.dataset_path)
    print(f"  Loaded {len(dataset)} samples.\n")

    # ── 2. evaluate ──────────────────────────────────────────────────── #
    print("Running Ragas evaluation (this may take a few minutes)...")
    engine = EvaluationEngine(settings)
    eval_result = engine.run(dataset)
    print("  Evaluation complete.\n")

    # ── 3. diagnose ──────────────────────────────────────────────────── #
    use_llm = not args.no_llm_diagnostics
    if use_llm:
        print("Running LLM-powered diagnostics...")
    else:
        print("Running rule-based diagnostics (LLM analysis skipped)...")
    diagnostic_engine = DiagnosticEngine(settings)
    diagnostic_report = diagnostic_engine.run(eval_result, use_llm=use_llm)
    print(f"  {diagnostic_report.total_failures} failing samples diagnosed.\n")

    # ── 4. report ────────────────────────────────────────────────────── #
    reporter = ReportGenerator(settings.output_dir)
    json_path = reporter.save_json(eval_result, diagnostic_report)
    print(f"JSON report saved to: {json_path}\n")

    reporter.print_cli_summary(eval_result, diagnostic_report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
