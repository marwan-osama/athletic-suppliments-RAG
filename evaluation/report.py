"""Report generation — JSON file + formatted CLI summary.

Produces:
1. A timestamped JSON report in ``eval_results/`` with per-sample scores,
   failure flags, diagnostic suggestions, and aggregate metrics.
2. A colour-coded CLI table for quick human review.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .diagnostics import DiagnosticReport
from .evaluate_rag import EvalResult

# ── ANSI colours for CLI output ──────────────────────────────────────── #

_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


class ReportGenerator:
    """Combine evaluation results and diagnostics into reports."""

    def __init__(self, output_dir: str | Path = "./eval_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ── JSON report ──────────────────────────────────────────────────── #

    def save_json(
        self,
        eval_result: EvalResult,
        diagnostic_report: DiagnosticReport,
    ) -> Path:
        """Write a comprehensive JSON report and return the file path."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self.output_dir / f"eval_report_{timestamp}.json"

        report: Dict[str, Any] = {
            "metadata": {
                "timestamp": timestamp,
                "threshold": eval_result.threshold,
                "total_samples": len(eval_result.samples),
                "total_failures": diagnostic_report.total_failures,
            },
            "aggregate_scores": eval_result.aggregate,
            "samples": [],
            "prioritised_actions": diagnostic_report.prioritised_actions,
        }

        # Build a lookup from question → diagnosis.
        diagnosis_map = {d.question: d for d in diagnostic_report.diagnoses}

        for sample in eval_result.samples:
            sample_dict: Dict[str, Any] = {
                "question": sample.question,
                "ground_truth": sample.ground_truth,
                "answer": sample.answer,
                "contexts": sample.contexts,
                "scores": sample.scores,
                "passed": len(sample.failure_flags) == 0,
                "failure_flags": sample.failure_flags,
            }

            diagnosis = diagnosis_map.get(sample.question)
            if diagnosis:
                sample_dict["diagnostics"] = {
                    "category": diagnosis.category,
                    "rule_suggestions": diagnosis.rule_suggestions,
                    "llm_analysis": diagnosis.llm_analysis,
                }

            report["samples"].append(sample_dict)

        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # ── CLI summary ──────────────────────────────────────────────────── #

    @staticmethod
    def print_cli_summary(
        eval_result: EvalResult,
        diagnostic_report: DiagnosticReport,
    ) -> None:
        """Print a human-readable, colour-coded summary to stdout."""
        threshold = eval_result.threshold

        # ── header ───────────────────────────────────────────────────── #
        print(f"\n{_BOLD}{'=' * 72}")
        print(f"  RAG EVALUATION REPORT")
        print(f"{'=' * 72}{_RESET}\n")

        # ── aggregate scores ─────────────────────────────────────────── #
        print(f"{_BOLD}Aggregate Scores (threshold = {threshold}):{_RESET}\n")
        for metric, score in eval_result.aggregate.items():
            colour = _GREEN if score >= threshold else _RED
            status = "PASS" if score >= threshold else "FAIL"
            bar = _score_bar(score)
            label = metric.replace("_", " ").title()
            print(f"  {label:<22} {colour}{score:.4f}{_RESET}  {bar}  [{status}]")

        # ── per-sample detail ────────────────────────────────────────── #
        print(f"\n{_BOLD}Per-Sample Results:{_RESET}\n")
        for index, sample in enumerate(eval_result.samples, start=1):
            passed = len(sample.failure_flags) == 0
            status_colour = _GREEN if passed else _RED
            status_text = "PASS" if passed else "FAIL"
            print(
                f"  {_BOLD}[{index}]{_RESET} {status_colour}[{status_text}]{_RESET} "
                f"{sample.question[:65]}"
            )
            for metric, score in sample.scores.items():
                colour = _GREEN if score >= threshold else _RED
                label = metric.replace("_", " ").title()
                print(f"       {label:<22} {colour}{score:.4f}{_RESET}")

            if sample.failure_flags:
                flags_str = ", ".join(sample.failure_flags)
                print(f"       {_YELLOW}Failing: {flags_str}{_RESET}")
            print()

        # ── diagnostics summary ──────────────────────────────────────── #
        if diagnostic_report.total_failures > 0:
            print(f"{_BOLD}{'─' * 72}")
            print(f"  DIAGNOSTICS ({diagnostic_report.total_failures} failing samples)")
            print(f"{'─' * 72}{_RESET}\n")

            for diagnosis in diagnostic_report.diagnoses:
                print(
                    f"  {_CYAN}▸ {diagnosis.question[:65]}{_RESET}"
                    f"  [{diagnosis.category}]"
                )
                for flag, suggestions in diagnosis.rule_suggestions.items():
                    label = flag.replace("_", " ").title()
                    print(f"    {_YELLOW}[{label}]{_RESET}")
                    for suggestion in suggestions[:2]:
                        print(f"      • {suggestion[:90]}")
                if diagnosis.llm_analysis:
                    print(f"    {_BOLD}LLM Analysis:{_RESET}")
                    # Wrap long lines.
                    for line in _wrap(diagnosis.llm_analysis, width=68):
                        print(f"      {line}")
                print()

            # ── prioritised actions ──────────────────────────────────── #
            if diagnostic_report.prioritised_actions:
                print(f"{_BOLD}  Top Priority Actions:{_RESET}")
                for index, action in enumerate(
                    diagnostic_report.prioritised_actions[:5], start=1
                ):
                    print(f"    {index}. {action[:85]}")
                print()

        else:
            print(f"  {_GREEN}All samples passed all metrics. 🎉{_RESET}\n")

        print(f"{_BOLD}{'=' * 72}{_RESET}\n")


# ── formatting helpers ───────────────────────────────────────────────── #

import math

def _score_bar(score: float, width: int = 20) -> str:
    """Return a visual bar for a score [0, 1]."""
    if math.isnan(score):
        score = 0.0
    
    filled = int(score * width)
    return "█" * filled + "░" * (width - filled)


def _wrap(text: str, width: int = 70) -> List[str]:
    """Naive word-wrap for terminal output."""
    words = text.split()
    lines: List[str] = []
    current: List[str] = []
    length = 0
    for word in words:
        if length + len(word) + 1 > width and current:
            lines.append(" ".join(current))
            current = [word]
            length = len(word)
        else:
            current.append(word)
            length += len(word) + 1
    if current:
        lines.append(" ".join(current))
    return lines
