"""Automated diagnostic & recommendation engine.

When a metric falls below the acceptance threshold, two things happen:

1. **Rule-based suggestions** — a lookup table maps each failing metric to
   concrete, actionable engineering recommendations.
2. **LLM-powered analysis** — the evaluator LLM (local or external) is
   prompted as a "Clinical Review Board" to produce a free-form diagnostic
   paragraph, catching patterns the rule engine misses.

The output is a list of ``Diagnosis`` objects, each carrying the failing
sample, its rule-based suggestions, and the LLM narrative.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rag.config import Settings

from .evaluate_rag import EvalResult, SampleResult

# ── rule-based suggestion tables ─────────────────────────────────────── #

_RETRIEVER_RECALL_SUGGESTIONS = [
    "Increase `top_k` from the current value — the retriever may be cutting "
    "off relevant passages that rank just below the threshold.",
    "Implement hybrid search: combine BM25 lexical matching with dense "
    "embeddings so that exact clinical terms are not missed.",
    "Experiment with domain-specific embedding models: BioBERT, Med-CPT, or "
    "PubMedBERT produce vectors tuned for biomedical vocabulary.",
    "Review chunking boundaries: if the ground-truth evidence spans a chunk "
    "split, the retriever cannot find it in a single vector.",
    "Raise the number of extra phrasings under Query expansion, or switch it "
    "on — a passage worded unlike the question is what it exists to catch.",
]

_RETRIEVER_PRECISION_SUGGESTIONS = [
    "Add a cross-encoder reranker (BGE-Reranker, Cohere Rerank, or a "
    "fine-tuned MiniLM) to re-score the top-k candidates after retrieval.",
    "Reduce `top_k` to keep only the most relevant passages — a high k "
    "dilutes precision with marginally related content.",
    "Tune `chunk_size` and `chunk_overlap`: smaller chunks increase "
    "specificity; larger overlap prevents information loss at boundaries.",
    "Enable metadata filtering (section headings, document type) to "
    "pre-filter the candidate pool before vector search.",
]

_FAITHFULNESS_SUGGESTIONS = [
    "Add strict citation enforcement to the system prompt: instruct the LLM "
    "to quote source numbers for every factual claim.",
    "Add refusal instructions: 'If the provided sources do not contain "
    "enough evidence, explicitly state that the information is unavailable.'",
    "Reduce the generation `temperature` toward 0 to minimise creative "
    "confabulation.",
    "Post-process the answer with a fact-checking pass: re-prompt the LLM "
    "to verify each claim against the provided context.",
    "Consider a constrained-decoding approach that limits generation to "
    "tokens present in or entailed by the source passages.",
]

_RELEVANCY_SUGGESTIONS = [
    "Adjust the system prompt for clinical conciseness: instruct the LLM to "
    "answer the specific question asked without tangential information.",
    "Add query-alignment instructions: 'Restate the question in your first "
    "sentence, then answer directly.'",
    "Reduce `max_tokens` to discourage verbose, off-topic generation.",
    "Implement answer-type detection: if the question asks for a dosage, "
    "ensure the answer leads with a number, not background context.",
]

_CHUNKING_SUGGESTIONS = [
    "Try semantic chunking: split on topic boundaries detected by embedding "
    "similarity rather than fixed character counts.",
    "Implement parent-document retrieval: index small chunks for precision, "
    "but return the full parent section for context.",
    "Use sentence-window retrieval: index individual sentences but expand "
    "the returned window to include surrounding sentences.",
    "Review `prepend_section=True` — if section headings are noisy, they "
    "may dilute the embedding signal.",
]

SUGGESTION_MAP: Dict[str, List[str]] = {
    "context_recall": _RETRIEVER_RECALL_SUGGESTIONS,
    "context_precision": _RETRIEVER_PRECISION_SUGGESTIONS,
    "faithfulness": _FAITHFULNESS_SUGGESTIONS,
    "answer_relevancy": _RELEVANCY_SUGGESTIONS,
}


# ── diagnostic data structures ───────────────────────────────────────── #

@dataclass
class Diagnosis:
    """Diagnostic output for a single failing sample."""

    question: str
    scores: Dict[str, float]
    failure_flags: List[str]
    rule_suggestions: Dict[str, List[str]] = field(default_factory=dict)
    llm_analysis: str = ""
    category: str = ""  # e.g. "Retriever", "Generation", "Ingestion"


@dataclass
class DiagnosticReport:
    """Full diagnostic output across all failing samples."""

    diagnoses: List[Diagnosis] = field(default_factory=list)
    prioritised_actions: List[str] = field(default_factory=list)

    @property
    def total_failures(self) -> int:
        return len(self.diagnoses)


# ── engine ───────────────────────────────────────────────────────────── #

_CLINICAL_REVIEW_PROMPT = """\
You are a Clinical Review Board evaluating a Medical RAG system.

A question-answer pair has failed quality thresholds. Analyse the scores and
the content below, then write a concise diagnostic paragraph that:
1. Identifies the most likely ROOT CAUSE of each failing metric.
2. References specific content from the question, answer, or contexts.
3. Suggests one concrete next engineering action per failing metric.

Failing metrics (threshold = {threshold}):
{metric_block}

Question: {question}
Ground Truth: {ground_truth}
Generated Answer: {answer}
Retrieved Contexts:
{contexts}

Write your analysis as a single paragraph. Be specific, clinical, and
actionable. Do NOT restate the scores — focus on WHY they failed.
"""


class DiagnosticEngine:
    """Diagnose failures and produce actionable suggestions.

    Combines deterministic rule-based lookup with an LLM "Clinical Review
    Board" analysis for nuanced, content-aware diagnostics.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()
        self.llm: Optional[Any] = None
        # LLM is lazily initialised so the engine works in offline mode.

    def run(
        self, eval_result: EvalResult, use_llm: Optional[bool] = None
    ) -> DiagnosticReport:
        """Diagnose every sample that has at least one failing metric.

        `use_llm` defaults to the `eval_llm_diagnostics` setting; pass it
        explicitly to override for one run.
        """
        if use_llm is None:
            use_llm = self.settings.eval_llm_diagnostics
        diagnoses: List[Diagnosis] = []

        for sample in eval_result.samples:
            if not sample.failure_flags:
                continue  # all metrics passed
            diagnosis = self._diagnose_sample(sample, eval_result.threshold, use_llm)
            diagnoses.append(diagnosis)

        prioritised = self._prioritise(diagnoses)

        return DiagnosticReport(
            diagnoses=diagnoses,
            prioritised_actions=prioritised,
        )

    # ── per-sample diagnosis ─────────────────────────────────────────── #

    def _diagnose_sample(
        self, sample: SampleResult, threshold: float, use_llm: bool
    ) -> Diagnosis:
        # ── rule-based suggestions ───────────────────────────────────── #
        rule_suggestions: Dict[str, List[str]] = {}
        for flag in sample.failure_flags:
            rule_suggestions[flag] = SUGGESTION_MAP.get(flag, [])

        # If multiple retrieval metrics fail, also suggest chunking changes.
        retrieval_failures = {"context_recall", "context_precision"}
        if len(retrieval_failures & set(sample.failure_flags)) == 2:
            rule_suggestions["ingestion_chunking"] = _CHUNKING_SUGGESTIONS

        # ── categorise ───────────────────────────────────────────────── #
        category = self._categorise(sample.failure_flags)

        # ── LLM analysis ────────────────────────────────────────────── #
        llm_analysis = ""
        if use_llm:
            llm_analysis = self._llm_analyse(sample, threshold)

        return Diagnosis(
            question=sample.question,
            scores=sample.scores,
            failure_flags=sample.failure_flags,
            rule_suggestions=rule_suggestions,
            llm_analysis=llm_analysis,
            category=category,
        )

    @staticmethod
    def _categorise(flags: List[str]) -> str:
        retrieval = {"context_recall", "context_precision"}
        generation = {"faithfulness", "answer_relevancy"}
        has_retrieval = bool(set(flags) & retrieval)
        has_generation = bool(set(flags) & generation)
        if has_retrieval and has_generation:
            return "Retriever + Generation"
        if has_retrieval:
            return "Retriever"
        return "Generation"

    # ── LLM-powered analysis ─────────────────────────────────────────── #

    def _get_llm(self) -> Any:
        # Imported here rather than at module scope: langchain is only needed
        # when diagnostics actually run, and the app imports this module to
        # decide whether to offer the button at all.
        from langchain_openai import ChatOpenAI

        if self.llm is None:
            base_url, model, _ = self.settings.eval_endpoint()
            self.llm = ChatOpenAI(
                model=model,
                openai_api_base=base_url,
                openai_api_key=self.settings.api_key or "not-needed",
                temperature=0.2,
                request_timeout=self.settings.eval_timeout,
            )
        return self.llm

    def _llm_analyse(self, sample: SampleResult, threshold: float) -> str:
        metric_block = "\n".join(
            f"  - {flag}: {sample.scores.get(flag, 0.0):.2f}"
            for flag in sample.failure_flags
        )
        contexts_block = "\n".join(
            f"  [{i + 1}] {ctx[:500]}" for i, ctx in enumerate(sample.contexts)
        )
        prompt = _CLINICAL_REVIEW_PROMPT.format(
            threshold=threshold,
            metric_block=metric_block,
            question=sample.question,
            ground_truth=sample.ground_truth,
            answer=sample.answer,
            contexts=contexts_block,
        )
        try:
            response = self._get_llm().invoke(prompt)
            return response.content.strip()
        except Exception as exc:  # noqa: BLE001
            return f"[LLM analysis unavailable: {exc}]"

    # ── prioritisation ───────────────────────────────────────────────── #

    @staticmethod
    def _prioritise(diagnoses: List[Diagnosis]) -> List[str]:
        """Rank actions by how many samples they would fix."""
        action_counts: Dict[str, int] = {}
        for diagnosis in diagnoses:
            for flag, suggestions in diagnosis.rule_suggestions.items():
                for suggestion in suggestions[:2]:  # top 2 per flag
                    key = f"[{flag}] {suggestion}"
                    action_counts[key] = action_counts.get(key, 0) + 1

        # Sort by frequency (most impactful first), then alphabetically.
        return [
            action
            for action, _ in sorted(
                action_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
