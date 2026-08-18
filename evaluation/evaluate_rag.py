"""Core evaluation engine — 4-metric scoring via Ragas 0.4.x.

Metrics (scored independently):
    1. Context Recall     – did the retriever capture all clinical evidence?
    2. Context Precision  – are the top-k chunks directly relevant?
    3. Faithfulness       – is the answer grounded in the retrieved docs?
    4. Answer Relevancy   – does the answer address the clinical question?

Medical acronym normalisation is applied as a pre-processing step before
scoring so that "EPA" and "eicosapentaenoic acid" are treated equivalently.
"""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from ragas import evaluate
from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.run_config import RunConfig
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

from .config import EvalSettings

# Suppress the deprecation warnings from ragas.metrics (they still work).
warnings.filterwarnings("ignore", message=".*Importing.*from 'ragas.metrics'.*")

# ── medical acronym map ──────────────────────────────────────────────── #
# Common athletic / clinical acronyms that should match their expansions.

MEDICAL_ACRONYMS: Dict[str, str] = {
    "EPA": "eicosapentaenoic acid",
    "DHA": "docosahexaenoic acid",
    "BCAA": "branched-chain amino acid",
    "BCAAs": "branched-chain amino acids",
    "HMB": "beta-hydroxy beta-methylbutyrate",
    "PCr": "phosphocreatine",
    "ATP": "adenosine triphosphate",
    "VO2max": "maximal oxygen consumption",
    "RDA": "recommended dietary allowance",
    "UL": "tolerable upper intake level",
    "ACSM": "American College of Sports Medicine",
    "ISSN": "International Society of Sports Nutrition",
    "NCAA": "National Collegiate Athletic Association",
    "GI": "gastrointestinal",
    "BMI": "body mass index",
    "RPE": "rating of perceived exertion",
    "1RM": "one-repetition maximum",
    "DOMS": "delayed onset muscle soreness",
    "NSAID": "nonsteroidal anti-inflammatory drug",
    "NSAIDs": "nonsteroidal anti-inflammatory drugs",
}

_ACRONYM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in MEDICAL_ACRONYMS) + r")\b"
)


def normalize_medical_text(text: str) -> str:
    """Expand medical acronyms so scoring is terminology-agnostic."""
    return _ACRONYM_PATTERN.sub(
        lambda match: f"{match.group(0)} ({MEDICAL_ACRONYMS[match.group(0)]})",
        text,
    )


# ── result container ─────────────────────────────────────────────────── #

@dataclass
class SampleResult:
    """Evaluation scores for a single Q&A sample."""

    question: str
    ground_truth: str
    answer: str
    contexts: List[str]
    scores: Dict[str, float] = field(default_factory=dict)
    failure_flags: List[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """Full evaluation output: per-sample + aggregates."""

    samples: List[SampleResult] = field(default_factory=list)
    aggregate: Dict[str, float] = field(default_factory=dict)
    threshold: float = 0.8


# ── Ragas 0.4.x column mapping ───────────────────────────────────────── #
# Our golden dataset uses user-friendly names; Ragas 0.4.x uses these:
#   question     -> user_input
#   contexts     -> retrieved_contexts
#   ground_truth -> reference
#   answer       -> response

RAGAS_COLUMN_MAP = {
    "question": "user_input",
    "ground_truth": "reference",
    "contexts": "retrieved_contexts",
    "answer": "response",
}

# Metric name -> Ragas column name in the output DataFrame.
METRIC_NAMES = [
    "context_recall",
    "context_precision",
    "faithfulness",
    "answer_relevancy",
]


# ── engine ───────────────────────────────────────────────────────────── #

class EvaluationEngine:
    """Run the four Ragas metrics against a golden dataset.

    Uses ``langchain-openai``'s ``ChatOpenAI`` wrapper which speaks the
    OpenAI-compatible protocol that both LM Studio and hosted gateways
    serve — so switching is just a URL change.
    """

    METRICS = [context_recall, context_precision, faithfulness, answer_relevancy]

    def __init__(self, settings: Optional[EvalSettings] = None):
        self.settings = settings or EvalSettings.from_env()

        raw_llm = ChatOpenAI(
            model=self.settings.eval_llm_model,
            openai_api_base=self.settings.eval_llm_base_url,
            openai_api_key=self.settings.eval_llm_api_key or "not-needed",
            temperature=0.0,
            request_timeout=300,
        )
        raw_embeddings = OpenAIEmbeddings(
            model=self.settings.eval_embed_model,
            openai_api_base=self.settings.eval_llm_base_url,
            openai_api_key=self.settings.eval_llm_api_key or "not-needed",
        )

        # Ragas 0.4.x requires its own wrapper types.
        self.llm = LangchainLLMWrapper(raw_llm)
        self.embeddings = LangchainEmbeddingsWrapper(raw_embeddings)

    def run(self, records: List[Dict[str, Any]]) -> EvalResult:
        """Score every sample against the four metrics.

        ``records`` is a list of dicts with keys:
        ``question``, ``ground_truth``, ``contexts``, ``answer``.

        Returns an ``EvalResult`` with per-sample scores, failure flags,
        and aggregate means.
        """
        # ── optional medical normalisation ───────────────────────────── #
        if self.settings.normalize_acronyms:
            records = [self._normalize_record(r) for r in records]

        # ── build Ragas EvaluationDataset ─────────────────────────────── #
        samples = []
        for record in records:
            samples.append(SingleTurnSample(
                user_input=record["question"],
                retrieved_contexts=record["contexts"],
                reference=record["ground_truth"],
                response=record["answer"],
            ))
        dataset = EvaluationDataset(samples=samples)

        # ── Ragas evaluation ─────────────────────────────────────────── #
        ragas_result = evaluate(
            dataset=dataset,
            metrics=self.METRICS,
            llm=self.llm,
            embeddings=self.embeddings,
            run_config=RunConfig(max_workers=1, timeout=180),
        )

        # ── extract per-sample scores ────────────────────────────────── #
        df = ragas_result.to_pandas()
        sample_results: List[SampleResult] = []

        for idx, row in df.iterrows():
            scores = {}
            for metric in METRIC_NAMES:
                value = row.get(metric)
                scores[metric] = float(value) if value is not None else 0.0

            flags = [
                metric
                for metric, score in scores.items()
                if score < self.settings.threshold
            ]
            sample_results.append(
                SampleResult(
                    question=records[idx]["question"],
                    ground_truth=records[idx]["ground_truth"],
                    answer=records[idx]["answer"],
                    contexts=records[idx]["contexts"],
                    scores=scores,
                    failure_flags=flags,
                )
            )

        # ── aggregates ───────────────────────────────────────────────── #
        aggregate = {}
        for metric in METRIC_NAMES:
            values = [s.scores.get(metric, 0.0) for s in sample_results]
            aggregate[metric] = sum(values) / len(values) if values else 0.0

        return EvalResult(
            samples=sample_results,
            aggregate=aggregate,
            threshold=self.settings.threshold,
        )

    # ── helpers ──────────────────────────────────────────────────────── #

    @staticmethod
    def _normalize_record(record: Dict[str, Any]) -> Dict[str, Any]:
        """Expand medical acronyms across all text fields."""
        return {
            **record,
            "question": normalize_medical_text(record.get("question", "")),
            "ground_truth": normalize_medical_text(record.get("ground_truth", "")),
            "answer": normalize_medical_text(record.get("answer", "")),
            "contexts": [
                normalize_medical_text(ctx)
                for ctx in record.get("contexts", [])
            ],
        }
