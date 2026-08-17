"""Configuration for the whole pipeline, in one place."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

DEFAULT_URL = (
    "https://ods.od.nih.gov/factsheets/"
    "ExerciseAndAthleticPerformance-HealthProfessional/"
)

EMBED_MODEL = "nvidia/llama-nemotron-embed-vl-1b-v2:free"
LLM_MODEL = "nvidia/nemotron-nano-9b-v2:free"


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal `.env` reader — avoids a dependency for six lines of parsing.

    Existing environment variables always win, so `OPENROUTER_API_KEY=...
    streamlit run app.py` still overrides the file.
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


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean environment variable, accepting the usual spellings."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    """Everything tunable. `Settings.from_env()` is the normal entry point."""

    # --- credentials / models (OpenRouter, one key for both) ---
    api_key: Optional[str] = None
    embed_model: str = EMBED_MODEL
    llm_model: str = LLM_MODEL
    base_url: str = "https://openrouter.ai/api/v1"
    # The `:free` variants allow roughly 20 requests/minute plus a daily cap, so
    # requests are paced rather than fired off in parallel bursts.
    requests_per_minute: int = 20
    embed_batch_size: int = 16
    # The embedding model is asymmetric — it was trained with these prefixes.
    document_prefix: str = "passage: "
    query_prefix: str = "query: "

    # --- source ---
    source: str = DEFAULT_URL
    source_url: str = DEFAULT_URL  # used to resolve relative links in local files
    cache_dir: Path = Path(".cache")

    # --- chunking ---
    chunk_size: int = 600
    chunk_overlap: int = 100
    min_chunk_chars: int = 80
    prepend_section: bool = True

    # --- augmentation ---
    # The master switch, from RAG_ENABLE_QUESTIONS. When false, no questions are
    # generated or indexed no matter what `questions_per_chunk` says.
    enable_questions: bool = True
    questions_per_chunk: int = 3
    question_workers: int = 4  # concurrency above the rate limit buys nothing

    # --- storage / retrieval ---
    db_path: Path = Path("./chroma_db")
    collection_base: str = "ods_health_facts"
    top_k: int = 5
    dedupe_by_chunk: bool = True

    def __post_init__(self) -> None:
        # Callers (CLI flags, Streamlit widgets) pass plain strings.
        self.db_path = Path(self.db_path)
        self.cache_dir = Path(self.cache_dir)
        # Collapsing the switch into the count here means everything downstream —
        # the pipeline, the collection name, the cost estimate — only has to look
        # at one number.
        if not self.enable_questions:
            self.questions_per_chunk = 0

    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_dotenv()
        settings = cls(
            api_key=os.getenv("OPENROUTER_API_KEY"),
            enable_questions=env_flag("RAG_ENABLE_QUESTIONS", default=True),
        )
        if source := os.getenv("RAG_SOURCE"):
            settings = replace(settings, source=source)
        return replace(settings, **overrides) if overrides else settings

    def with_(self, **overrides) -> "Settings":
        """Copy with fields replaced — used by the UI when sliders move."""
        return replace(self, **overrides)

    @property
    def collection_name(self) -> str:
        """Every parameter that changes the indexed vectors is part of the name.

        Different chunking settings produce genuinely different indexes, so
        keeping them in separate collections lets you switch settings in the UI
        (and compare them) without wiping and rebuilding each time. The embedder
        is in the name too: vectors from different models are not comparable.
        """
        return (
            f"{self.collection_base}__{self.embedder_tag}"
            f"_c{self.chunk_size}_o{self.chunk_overlap}"
            f"_q{self.questions_per_chunk}_m{self.min_chunk_chars}"
            f"_s{int(self.prepend_section)}"
        )

    @property
    def embedder_tag(self) -> str:
        """Short slug for the active embedder, for the collection name."""
        if not self.has_api_key:
            return "hash"
        model = self.embed_model.split("/")[-1].replace(":free", "")
        return re.sub(r"[^a-z0-9]+", "", model.lower())[:12]

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)
