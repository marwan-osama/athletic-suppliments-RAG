"""Configuration for the evaluation pipeline.

Mirrors the pattern in ``rag.config`` — a frozen dataclass with an
``from_env()`` classmethod that reads ``.env`` and environment variables.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal ``.env`` reader — mirrors ``rag.config.load_dotenv``.

    Duplicated here so the evaluation package stays self-contained and
    doesn't pull in the full ``rag`` dependency tree (trafilatura, etc.).
    """
    env_path = Path(path)
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# ── defaults ────────────────────────────────────────────────────────── #

# Local LM Studio server — same endpoint the RAG pipeline uses.
_LOCAL_BASE_URL = "http://127.0.0.1:11434/v1"
_DEFAULT_LLM_MODEL = "gemma4:e2b-it-qat"
_DEFAULT_EMBED_MODEL = "embeddinggemma"

_DEFAULT_THRESHOLD = 0.8
_DEFAULT_OUTPUT_DIR = Path("./eval_results")
_DEFAULT_DATASET = Path(__file__).resolve().parent / "data" / "golden_dataset.json"


@dataclass
class EvalSettings:
    """Everything the evaluation pipeline needs to know.

    ``EvalSettings.from_env()`` is the normal entry point — it reads
    ``.env``, then environment variables, then any keyword overrides.
    """

    # ── evaluator LLM (judges the RAG output) ───────────────────────── #
    eval_llm_base_url: str = _LOCAL_BASE_URL
    eval_llm_api_key: Optional[str] = None
    eval_llm_model: str = _DEFAULT_LLM_MODEL
    eval_embed_model: str = _DEFAULT_EMBED_MODEL

    # ── scoring ──────────────────────────────────────────────────────── #
    threshold: float = _DEFAULT_THRESHOLD

    # ── paths ────────────────────────────────────────────────────────── #
    dataset_path: Path = field(default_factory=lambda: _DEFAULT_DATASET)
    output_dir: Path = field(default_factory=lambda: _DEFAULT_OUTPUT_DIR)

    # ── medical normalisation ────────────────────────────────────────── #
    normalize_acronyms: bool = True

    def __post_init__(self) -> None:
        self.dataset_path = Path(self.dataset_path)
        self.output_dir = Path(self.output_dir)

    @classmethod
    def from_env(cls, **overrides) -> "EvalSettings":
        load_dotenv()
        settings = cls(
            eval_llm_base_url=os.getenv("EVAL_LLM_BASE_URL", _LOCAL_BASE_URL),
            eval_llm_api_key=os.getenv("EVAL_LLM_API_KEY"),
            eval_llm_model=os.getenv("EVAL_LLM_MODEL", _DEFAULT_LLM_MODEL),
            eval_embed_model=os.getenv("EVAL_EMBED_MODEL", _DEFAULT_EMBED_MODEL),
        )
        # Apply any programmatic overrides last.
        if overrides:
            for key, value in overrides.items():
                if hasattr(settings, key):
                    object.__setattr__(settings, key, value)
        return settings
