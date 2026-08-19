"""Scoring — four Ragas metrics over what the pipeline actually produced.

    context_recall     did retrieval find the evidence the reference relies on?
    context_precision  are the chunks it returned actually about the question?
    faithfulness       is the answer grounded in those chunks?
    answer_relevancy   does the answer address the question asked?

The first two grade `Retriever`, the last two grade `Answerer` — which is what
makes a failing metric point at a stage rather than at "the RAG is bad".

Medical acronyms are expanded before scoring so that "HMB" and
"beta-hydroxy beta-methylbutyrate" are not treated as different claims.

Ragas is imported lazily: it pulls in langchain and datasets, and neither the
pipeline nor the Streamlit app should need them to start.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rag.config import Settings

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

# Longest first, so "BCAAs" is not matched as "BCAA" with a stray "s".
_ACRONYM_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(MEDICAL_ACRONYMS, key=len, reverse=True)) + r")\b"
)

METRIC_NAMES = [
    "context_recall",
    "context_precision",
    "faithfulness",
    "answer_relevancy",
]

# Which stage a failing metric implicates — the report groups by this.
METRIC_STAGE = {
    "context_recall": "retrieval",
    "context_precision": "retrieval",
    "faithfulness": "answering",
    "answer_relevancy": "answering",
}

INSTALL_HINT = (
    "Scoring needs ragas, which is not installed. "
    "Install it with:  .venv/bin/pip install -r requirements.txt"
)


class EvaluationUnavailable(RuntimeError):
    """Ragas (or one of its dependencies) is not installed."""


def available() -> bool:
    """Whether scoring can run — the UI greys out its button on False."""
    try:
        import ragas  # noqa: F401
    except Exception:  # noqa: BLE001 - a broken install is as good as a missing one
        return False
    return True


def normalize_medical_text(text: str) -> str:
    """Expand medical acronyms so scoring is terminology-agnostic."""
    return _ACRONYM_PATTERN.sub(
        lambda match: f"{match.group(0)} ({MEDICAL_ACRONYMS[match.group(0)]})",
        text,
    )


@dataclass
class SampleResult:
    """Scores for a single question, with what produced them."""

    question: str
    ground_truth: str
    answer: str
    contexts: List[str]
    scores: Dict[str, float] = field(default_factory=dict)
    failure_flags: List[str] = field(default_factory=list)
    retrieved: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def failing_stages(self) -> List[str]:
        """Which pipeline stages this sample implicates, in pipeline order."""
        stages = {METRIC_STAGE[flag] for flag in self.failure_flags}
        return [stage for stage in ("retrieval", "answering") if stage in stages]


@dataclass
class EvalResult:
    """Per-sample scores plus the aggregate over them."""

    samples: List[SampleResult] = field(default_factory=list)
    aggregate: Dict[str, float] = field(default_factory=dict)
    threshold: float = 0.8

    @property
    def passing(self) -> bool:
        return all(score >= self.threshold for score in self.aggregate.values())


class EvaluationEngine:
    """Run the four metrics over records the harness collected.

    The judge speaks the same OpenAI shape as the pipeline's own server, so by
    default it is the same LM Studio endpoint; `Settings.eval_endpoint()` is
    what points it somewhere else.
    """

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.from_env()

    def run(self, records: List[Dict[str, Any]]) -> EvalResult:
        """Score `records` — each needs question, ground_truth, contexts, answer."""
        if not records:
            return EvalResult(threshold=self.settings.eval_threshold)

        ragas = _load_ragas()
        graded = (
            [self._normalize(record) for record in records]
            if self.settings.eval_normalize_acronyms
            else records
        )

        base_url, model, embed_model = self.settings.eval_endpoint()
        # "not-needed" rather than "": LM Studio ignores the key, but the
        # OpenAI client refuses to start without one.
        key = self.settings.api_key or "not-needed"
        judge = ragas["LangchainLLMWrapper"](
            ragas["ChatOpenAI"](
                model=model, openai_api_base=base_url, openai_api_key=key,
                temperature=0.0, request_timeout=self.settings.eval_timeout,
            )
        )
        embeddings = ragas["LangchainEmbeddingsWrapper"](
            ragas["OpenAIEmbeddings"](
                model=embed_model, openai_api_base=base_url, openai_api_key=key,
                check_embedding_ctx_length=False,
            )
        )

        dataset = ragas["EvaluationDataset"](
            samples=[
                ragas["SingleTurnSample"](
                    user_input=record["question"],
                    retrieved_contexts=list(record["contexts"]),
                    reference=record["ground_truth"],
                    response=record["answer"],
                )
                for record in graded
            ]
        )
        scored = ragas["evaluate"](
            dataset=dataset,
            metrics=ragas["METRICS"],
            llm=judge,
            embeddings=embeddings,
            run_config=ragas["RunConfig"](
                max_workers=self.settings.eval_max_workers,
                timeout=self.settings.eval_timeout,
            ),
        )

        return self._collect(scored.to_pandas(), records)

    # -- internals ---------------------------------------------------------- #
    def _collect(self, frame, records: List[Dict[str, Any]]) -> EvalResult:
        """Turn the Ragas frame back into per-sample results and aggregates.

        Scores are read positionally against `records`, so the originals — not
        the acronym-expanded copies — are what the report shows.
        """
        samples: List[SampleResult] = []
        for position, (_, row) in enumerate(frame.iterrows()):
            scores = {name: _as_score(row.get(name)) for name in METRIC_NAMES}
            record = records[position]
            samples.append(
                SampleResult(
                    question=record["question"],
                    ground_truth=record["ground_truth"],
                    answer=record["answer"],
                    contexts=list(record["contexts"]),
                    scores=scores,
                    failure_flags=[
                        name for name, score in scores.items()
                        if score < self.settings.eval_threshold
                    ],
                    retrieved=record.get("retrieved", []),
                )
            )

        aggregate = {
            name: (
                sum(sample.scores[name] for sample in samples) / len(samples)
                if samples else 0.0
            )
            for name in METRIC_NAMES
        }
        return EvalResult(
            samples=samples,
            aggregate=aggregate,
            threshold=self.settings.eval_threshold,
        )

    @staticmethod
    def _normalize(record: Dict[str, Any]) -> Dict[str, Any]:
        """Expand medical acronyms across every text field."""
        return {
            **record,
            "question": normalize_medical_text(record.get("question", "")),
            "ground_truth": normalize_medical_text(record.get("ground_truth", "")),
            "answer": normalize_medical_text(record.get("answer", "")),
            "contexts": [
                normalize_medical_text(context)
                for context in record.get("contexts", [])
            ],
        }


def _as_score(value: Any) -> float:
    """Ragas returns NaN for a metric it could not compute; treat it as zero."""
    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if score != score else score  # NaN is the only value unequal to itself


def _load_ragas() -> Dict[str, Any]:
    """Import ragas on demand, with one clear message when it is missing."""
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas import evaluate
        from ragas.dataset_schema import EvaluationDataset, SingleTurnSample
        from ragas.embeddings import LangchainEmbeddingsWrapper
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
        from ragas.run_config import RunConfig
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise EvaluationUnavailable(INSTALL_HINT) from exc

    return {
        "ChatOpenAI": ChatOpenAI,
        "OpenAIEmbeddings": OpenAIEmbeddings,
        "evaluate": evaluate,
        "EvaluationDataset": EvaluationDataset,
        "SingleTurnSample": SingleTurnSample,
        "LangchainEmbeddingsWrapper": LangchainEmbeddingsWrapper,
        "LangchainLLMWrapper": LangchainLLMWrapper,
        "RunConfig": RunConfig,
        # Same order as METRIC_NAMES.
        "METRICS": [context_recall, context_precision, faithfulness, answer_relevancy],
    }
