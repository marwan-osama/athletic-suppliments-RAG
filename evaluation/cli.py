"""Command line entry point: `python -m evaluation <command>`.

    python -m evaluation run
    python -m evaluation run --dataset path/to/golden.csv --threshold 0.7
    python -m evaluation run --no-llm-diagnostics
    python -m evaluation run --eval-model gpt-4o --eval-base-url https://api.openai.com/v1
    python -m evaluation smoke

Every run asks the live pipeline each question in the golden set and grades what
comes back, so the index has to be built first (`python -m rag.cli build`).
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from datetime import datetime
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

# IDs of the 8 smoke-test questions (1-indexed, matching golden_dataset.json).
SMOKE_IDS = {1, 4, 9, 10, 13, 18, 20, 24}

# The original (pre-improvement) prompt, kept here so --prompt-version old
# can reproduce the baseline without reverting answering.py.
OLD_SYSTEM = None  # no system message
OLD_PROMPT = (
    "Answer the question using ONLY the numbered sources below. Cite the "
    "sources you use as [1], [2], and so on. If the sources do not contain "
    "the answer, say so plainly.\n\n"
    "Question: {question}\n\nSources:\n{sources}\n\nAnswer:"
)


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
        help="rule-based diagnosis only -- skips a generation call per failure",
    )

    smoke = commands.add_parser(
        "smoke",
        help="fast 8-question generation test -- no RAGAS scoring",
    )
    smoke.add_argument("--dataset", type=Path, help=".json golden set")
    smoke.add_argument("--output", type=Path, help="where the smoke report is written")
    smoke.add_argument(
        "--prompt-version",
        choices=["old", "new"],
        default="new",
        help="'old' uses the original minimal prompt; 'new' (default) uses the improved system+user prompt",
    )
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    values = vars(args)
    overrides = {
        field: values[name]
        for name, field in OVERRIDES.items()
        if values.get(name) is not None
    }
    if getattr(args, "no_llm_diagnostics", False):
        overrides["eval_llm_diagnostics"] = False
    return Settings.from_env(**overrides)


def _safe(text: str) -> str:
    """Make text safe for the Windows console (cp1252) and wrap it."""
    safe = text.encode("ascii", errors="replace").decode("ascii")
    return textwrap.fill(safe, width=80, break_long_words=False, break_on_hyphens=False)



def _generate_with_old_prompt(pipeline: RAGPipeline, question: str, hits) -> str:
    """Generate an answer using the original minimal prompt (no system message)."""
    from rag.answering import Answerer
    answerer = pipeline.answerer
    if answerer is None:
        return "Answerer not available."
    formatted = answerer._format(hits)
    prompt = OLD_PROMPT.format(question=question, sources=formatted)
    return answerer.client.complete(
        model=answerer.model_name,
        prompt=prompt,
        temperature=answerer.temperature,
        max_tokens=answerer.max_tokens,
        reasoning_effort=answerer.reasoning_effort or None,
        system=OLD_SYSTEM,
    )


def run_smoke(argv: Optional[List[str]] = None) -> int:
    """Run only the 8 smoke-test questions and print a readable comparison."""
    args = build_parser().parse_args(argv)
    settings = settings_from_args(args)
    pipeline = RAGPipeline(settings)
    prompt_version = getattr(args, "prompt_version", "new")

    print(f"Model      : {settings.llm_model}")
    print(f"Prompt     : {prompt_version}")
    print(f"Collection : {settings.collection_name} ({pipeline.index.count:,} rows)")
    print(f"Dataset    : {settings.eval_dataset_path}")
    print(f"Smoke IDs  : {sorted(SMOKE_IDS)}")
    print()

    dataset = load_dataset(settings.eval_dataset_path)
    subset = [row for row in dataset if row.get("id") in SMOKE_IDS]
    if not subset:
        print("No matching questions found in the dataset.", file=sys.stderr)
        return 1

    print(f"Running {len(subset)} smoke-test questions...\n")

    from .harness import check_ready
    check_ready(pipeline)

    results = []
    for i, row in enumerate(subset, start=1):
        qid = row.get("id", "?")
        question = row["question"]
        ground_truth = row.get("ground_truth", "")

        hits = pipeline.search(question)
        try:
            if prompt_version == "old":
                answer = _generate_with_old_prompt(pipeline, question, hits)
            else:
                answer = pipeline.answer(question, hits)
        except Exception as exc:
            answer = f"Error: {exc}"

        results.append({
            "id": qid,
            "question": question,
            "ground_truth": ground_truth,
            "generated_answer": answer,
            "prompt_version": prompt_version,
            "retrieved_chunks": [
                {"section": h.section, "text": h.text[:500]}
                for h in hits
            ],
        })

        print("=" * 70)
        print(f"Q{qid}: {question}")
        print("-" * 70)
        print(f"EXPECTED: {_safe(ground_truth)}")
        print("-" * 70)
        print(f"GENERATED: {_safe(answer)}")
        print("-" * 70)
        print(f"SOURCES: {', '.join(h.section or '?' for h in hits)}")
        print(f"  ({i}/{len(subset)})\n")

    # Save results for comparison
    output_dir = settings.eval_output_dir / "smoke"
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    model_slug = settings.llm_model.replace("/", "_").replace(":", "_")
    out_path = output_dir / f"smoke_{stamp}_{prompt_version}_{model_slug}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSmoke results saved: {out_path}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "smoke":
        return run_smoke(argv)

    settings = settings_from_args(args)
    pipeline = RAGPipeline(settings)
    base_url, model, embed_model = settings.eval_endpoint()

    print(f"Collection : {settings.collection_name} ({pipeline.index.count:,} rows)")
    print(f"Judge      : {model} . {embed_model} @ {base_url}")
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

    print("\nScoring (a few minutes -- the judge reads every sample)...")
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
