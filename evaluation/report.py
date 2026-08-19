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
from typing import Any, Dict, List, Optional

from rag.config import Settings
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
        settings: Optional[Settings] = None,
    ) -> Path:
        """Write a comprehensive JSON report to runs/ and models/ and return the run file path."""
        import re
        
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        
        clean_model = "unknown_model"
        if settings and settings.llm_model:
            clean_model = re.sub(r"[^a-zA-Z0-9_\-]", "_", settings.llm_model)

        metadata: Dict[str, Any] = {
            "timestamp": timestamp,
            "threshold": eval_result.threshold,
            "total_samples": len(eval_result.samples),
            "total_failures": diagnostic_report.total_failures,
        }
        
        if settings:
            metadata.update({
                "llm_model": settings.llm_model,
                "embed_model": settings.embed_model,
                "top_k": settings.top_k,
                "query_expansion_enabled": settings.query_expansions > 0,
                "query_expansions": settings.query_expansions,
                "question_augmentation_enabled": settings.questions_per_chunk > 0,
                "questions_per_chunk": settings.questions_per_chunk,
                "answer_temperature": settings.answer_temperature,
                "reasoning_effort": settings.reasoning_effort,
                "eval_dataset_path": str(settings.eval_dataset_path),
                "settings": settings.to_dict()
            })

        report: Dict[str, Any] = {
            "metadata": metadata,
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
                # Which chunks were graded, and how they were ranked — so a
                # score can be traced back to the retrieval that produced it.
                "retrieved": sample.retrieved,
                "scores": sample.scores,
                "passed": len(sample.failure_flags) == 0,
                "failure_flags": sample.failure_flags,
                "failing_stages": sample.failing_stages,
            }

            diagnosis = diagnosis_map.get(sample.question)
            if diagnosis:
                sample_dict["diagnostics"] = {
                    "category": diagnosis.category,
                    "rule_suggestions": diagnosis.rule_suggestions,
                    "llm_analysis": diagnosis.llm_analysis,
                }

            report["samples"].append(sample_dict)

        # Ensure the subdirectories exist
        runs_dir = self.output_dir / "runs"
        models_dir = self.output_dir / "models" / clean_model
        
        runs_dir.mkdir(parents=True, exist_ok=True)
        models_dir.mkdir(parents=True, exist_ok=True)

        run_path = runs_dir / f"run_{timestamp}_{clean_model}.json"
        model_path = models_dir / "latest_report.json"

        content = json.dumps(report, indent=2, ensure_ascii=False)
        run_path.write_text(content, encoding="utf-8")
        model_path.write_text(content, encoding="utf-8")
        
        # ── generate markdown report ────────────────────────────────────────── #
        md = []
        md.append(f"# RAG Evaluation Report: `{metadata.get('llm_model', 'Unknown')}`")
        md.append(f"- **Timestamp:** {timestamp}")
        md.append(f"- **Embedding Model:** `{metadata.get('embed_model', 'Unknown')}`")
        md.append(f"- **Top-K Retrieval Depth:** `{metadata.get('top_k', 'Unknown')}`")
        md.append(f"- **Query Expansion:** `{'Enabled' if metadata.get('query_expansion_enabled') else 'Disabled'}`")
        md.append(f"- **Question Augmentation:** `{'Enabled' if metadata.get('question_augmentation_enabled') else 'Disabled'}`")
        md.append(f"- **Acceptance Threshold:** `{metadata.get('threshold', 0.8)}`\n")

        # Inconsistent retrieval warning check
        agg = eval_result.aggregate
        has_ret_metrics = "retrieval_hit_rate" in agg
        retrieval_all_zero = (
            has_ret_metrics and
            agg.get("retrieval_hit_rate", 0.0) == 0.0 and
            agg.get("retrieval_recall", 0.0) == 0.0 and
            agg.get("retrieval_precision", 0.0) == 0.0 and
            agg.get("retrieval_mrr", 0.0) == 0.0
        )
        any_retrieved = any(len(sample.retrieved) > 0 for sample in eval_result.samples)
        warning_needed = retrieval_all_zero and any_retrieved

        if warning_needed:
            md.append("> [!WARNING]")
            md.append("> **Retrieval evaluation may need investigation:** retrieval metrics are 0 despite apparently relevant retrieved chunks. Check the retrieval ground-truth/expected-chunk mapping before changing the retriever.\n")

        md.append("## Aggregate Scores\n")
        md.append("| Metric | Score | Status | Description |")
        md.append("| :--- | :--- | :--- | :--- |")
        
        METRIC_DESCRIPTIONS = {
            "context_recall": "How much of the information needed to answer the question was retrieved.",
            "context_precision": "How much of the retrieved context was actually relevant.",
            "faithfulness": "Whether the generated answer is supported by the retrieved context.",
            "answer_relevancy": "Whether the generated answer actually addresses the user's question.",
            "retrieval_hit_rate": "Whether at least one expected relevant chunk was retrieved.",
            "retrieval_recall": "How much of the expected relevant retrieval set was retrieved.",
            "retrieval_precision": "How much of the retrieved chunks were relevant.",
            "retrieval_mrr": "How highly the first relevant result was ranked.",
        }

        for name, score in eval_result.aggregate.items():
            status = "🟢 PASS" if score >= eval_result.threshold else "🔴 FAIL"
            label = name.replace("_", " ").title()
            desc = METRIC_DESCRIPTIONS.get(name, "-")
            md.append(f"| **{label}** | `{score:.4f}` | {status} | {desc} |")
        md.append("\n")

        # Interpretation Matrix Section
        md.append("## Interpretation Matrix\n")
        md.append("| Scenario | Explanation |")
        md.append("| :--- | :--- |")
        
        c_precision = agg.get("context_precision", 0.0)
        c_recall = agg.get("context_recall", 0.0)
        faith = agg.get("faithfulness", 0.0)
        a_relevancy = agg.get("answer_relevancy", 0.0)
        t = eval_result.threshold

        if c_precision >= t and c_recall < t:
            md.append("| **High Precision + Low Recall** | Retrieved chunks are relevant, but some required information may be missing. |")
        elif c_recall >= t and c_precision < t:
            md.append("| **High Recall + Low Precision** | The required information is being retrieved, but too much irrelevant context is also being retrieved. |")
        else:
            md.append("| **Retrieval Balance** | Retrieved chunks have mixed relevance and completion compared to expected ground truth. |")
            
        if faith < t:
            md.append("| **Low Faithfulness** | The generated answer may contain claims that are not sufficiently supported by the retrieved context. |")
        if a_relevancy < t:
            md.append("| **Low Answer Relevancy** | The generated answer may not directly answer the question. |")
        md.append("\n")

        md.append(f"## Failure Diagnostics ({diagnostic_report.total_failures} / {len(eval_result.samples)} failed)\n")
        if diagnostic_report.total_failures > 0:
            md.append("### Recommended Top Priorities:")
            for idx, action in enumerate(diagnostic_report.prioritised_actions[:5], start=1):
                md.append(f"{idx}. {action}")
            md.append("\n")

            md.append("### Per-Question Detailed Results:\n")
            for idx, sample in enumerate(eval_result.samples, start=1):
                passed = len(sample.failure_flags) == 0
                status_str = "🟢 PASS" if passed else "🔴 FAIL"
                md.append(f"#### {idx}. {sample.question} ({status_str})")
                md.append(f"- **Ground Truth:** {sample.ground_truth}")
                md.append(f"- **Generated Answer:** {sample.answer}")
                
                # Show retrieved contexts
                md.append("- **Retrieved Contexts:**")
                for c_idx, ctx in enumerate(sample.contexts, start=1):
                    md.append(f"  - [{c_idx}] {ctx[:300]}...")
                
                scores_str = ", ".join(f"{k.replace('_', ' ').title()}: `{v:.4f}`" for k, v in sample.scores.items())
                md.append(f"- **Scores:** {scores_str}")
                
                # Deduce dynamic diagnostic interpretation
                likely_meaning = "The retriever and generator are performing well."
                if sample.failure_flags:
                    md.append(f"- **Failing Stage / Metrics:** `{', '.join(sample.failing_stages)}` ({', '.join(sample.failure_flags)})")
                    diag = diagnosis_map.get(sample.question)
                    if diag:
                        md.append("- **Rule Suggestions:**")
                        for flag, suggestions in diag.rule_suggestions.items():
                            for sug in suggestions[:1]:
                                md.append(f"  - *{flag.replace('_', ' ').title()}:* {sug}")
                        if diag.llm_analysis:
                            md.append(f"- **LLM Analysis:** {diag.llm_analysis}")
                    
                    meanings = []
                    ret_flags = {"context_recall", "context_precision", "retrieval_hit_rate", "retrieval_recall"}
                    if set(sample.failure_flags) & ret_flags:
                        meanings.append("The retriever missed the target chunks or the ground-truth mapping is outdated.")
                    if "faithfulness" in sample.failure_flags:
                        meanings.append("The LLM hallucinated or introduced information not present in the retrieved chunks.")
                    if "answer_relevancy" in sample.failure_flags:
                        meanings.append("The LLM was off-topic or did not directly answer the user's prompt.")
                    likely_meaning = " ".join(meanings)
                
                md.append(f"- **What this likely means:** *{likely_meaning}*\n")
                md.append("")
        else:
            md.append("All questions passed all metrics successfully! 🟢")

        md_content = "\n".join(md)
        run_md_path = runs_dir / f"run_{timestamp}_{clean_model}.md"
        model_md_path = models_dir / "latest_report.md"
        
        run_md_path.write_text(md_content, encoding="utf-8")
        model_md_path.write_text(md_content, encoding="utf-8")

        return run_path

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

        # Inconsistent retrieval warning check
        agg = eval_result.aggregate
        has_ret_metrics = "retrieval_hit_rate" in agg
        retrieval_all_zero = (
            has_ret_metrics and
            agg.get("retrieval_hit_rate", 0.0) == 0.0 and
            agg.get("retrieval_recall", 0.0) == 0.0 and
            agg.get("retrieval_precision", 0.0) == 0.0 and
            agg.get("retrieval_mrr", 0.0) == 0.0
        )
        any_retrieved = any(len(sample.retrieved) > 0 for sample in eval_result.samples)
        if retrieval_all_zero and any_retrieved:
            print(f"{_YELLOW}⚠️  Retrieval evaluation may need investigation: retrieval metrics are 0 despite apparently relevant retrieved chunks. Check the retrieval ground-truth/expected-chunk mapping before changing the retriever.{_RESET}\n")

        # ── aggregate scores ─────────────────────────────────────────── #
        print(f"{_BOLD}Aggregate Scores (threshold = {threshold}):{_RESET}\n")
        
        METRIC_DESCRIPTIONS = {
            "context_recall": "How much of the information needed to answer the question was retrieved.",
            "context_precision": "How much of the retrieved context was actually relevant.",
            "faithfulness": "Whether the generated answer is supported by the retrieved context.",
            "answer_relevancy": "Whether the generated answer actually addresses the user's question.",
            "retrieval_hit_rate": "Whether at least one expected relevant chunk was retrieved.",
            "retrieval_recall": "How much of the expected relevant retrieval set was retrieved.",
            "retrieval_precision": "How much of the retrieved chunks were relevant.",
            "retrieval_mrr": "How highly the first relevant result was ranked.",
        }

        def get_interpretation_cli(metric: str, score: float, t: float) -> str:
            passed = score >= t
            if metric == "context_recall":
                return "Required information successfully retrieved." if passed else "Some required information may be missing."
            elif metric == "context_precision":
                return "Retrieved contexts are highly relevant." if passed else "Irrelevant context is being retrieved."
            elif metric == "faithfulness":
                return "The generated answer is grounded in retrieved context." if passed else "The generated answer may contain claims that are not sufficiently supported by the retrieved context."
            elif metric == "answer_relevancy":
                return "The answer directly addresses the question." if passed else "The generated answer may not directly answer the question."
            elif metric == "retrieval_hit_rate":
                return "At least one expected relevant chunk was retrieved." if passed else "No expected relevant chunks were retrieved."
            elif metric == "retrieval_recall":
                return "Retrieved most expected relevant chunks." if passed else "Missing expected relevant chunks."
            elif metric == "retrieval_precision":
                return "Retrieved chunks are highly precise." if passed else "High dilution of relevant chunks with irrelevant ones."
            elif metric == "retrieval_mrr":
                return "First relevant result is highly ranked." if passed else "First relevant result is ranked low."
            return ""

        for metric, score in eval_result.aggregate.items():
            colour = _GREEN if score >= threshold else _RED
            status = "PASS" if score >= threshold else "FAIL"
            bar = _score_bar(score)
            label = metric.replace("_", " ").title()
            print(f"  {label:<22} {colour}{score:.4f}{_RESET}  {bar}  [{status}]")
            desc = METRIC_DESCRIPTIONS.get(metric, "")
            interpret = get_interpretation_cli(metric, score, threshold)
            print(f"    Description   : {desc}")
            print(f"    Interpretation: {interpret}\n")

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
            print(f"{_BOLD}{'-' * 72}")
            print(f"  DIAGNOSTICS ({diagnostic_report.total_failures} failing samples)")
            print(f"{'-' * 72}{_RESET}\n")

            for diagnosis in diagnostic_report.diagnoses:
                print(
                    f"  {_CYAN}* {diagnosis.question[:65]}{_RESET}"
                    f"  [{diagnosis.category}]"
                )
                for flag, suggestions in diagnosis.rule_suggestions.items():
                    label = flag.replace("_", " ").title()
                    print(f"    {_YELLOW}[{label}]{_RESET}")
                    for suggestion in suggestions[:2]:
                        print(f"      - {suggestion[:90]}")
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
            print(f"  {_GREEN}All samples passed all metrics!{_RESET}\n")

        print(f"{_BOLD}{'=' * 72}{_RESET}\n")


# ── formatting helpers ───────────────────────────────────────────────── #

import math

def _score_bar(score: float, width: int = 20) -> str:
    """Return a visual bar for a score [0, 1]."""
    if math.isnan(score):
        score = 0.0
    
    filled = int(score * width)
    return "#" * filled + "-" * (width - filled)


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
