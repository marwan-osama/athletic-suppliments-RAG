"""Configuration for the whole pipeline, in one place."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from .llm import LOCAL_BASE_URL

DEFAULT_URL = (
    "https://ods.od.nih.gov/factsheets/"
    "ExerciseAndAthleticPerformance-HealthProfessional/"
)

# Loaded in LM Studio; `python -m rag.cli models` lists what the server offers.
EMBED_MODEL = "embeddinggemma"
LLM_MODEL = "gemma4:e2b-it-qat"

# EmbeddingGemma's own instruction templates. Measured on a creatine query
# against a matching and a mismatched passage, these separated the two by 0.47
# versus 0.35 with no prefixes — so they stay.
DOCUMENT_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "


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

    # --- models (LM Studio's local server, one endpoint for both) ---
    base_url: str = LOCAL_BASE_URL
    api_key: Optional[str] = None  # LM Studio needs none; hosted gateways do
    embed_model: str = EMBED_MODEL
    llm_model: str = LLM_MODEL
    embed_dimensions: int = 768  # what embeddinggemma-300m returns
    embed_batch_size: int = 16
    # Local models have no quota, so nothing is paced. Set this above 0 when
    # pointing `base_url` at a rate-limited hosted endpoint.
    requests_per_minute: int = 0
    # The embedding model is asymmetric — it was trained with these prefixes.
    document_prefix: str = DOCUMENT_PREFIX
    query_prefix: str = QUERY_PREFIX
    # Skip the server entirely and use word-overlap vectors (RAG_OFFLINE).
    offline: bool = False

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
    question_workers: int = 8  # concurrency above the rate limit buys nothing

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
            api_key=os.getenv("LLM_API_KEY"),
            enable_questions=env_flag("RAG_ENABLE_QUESTIONS", default=True),
            offline=env_flag("RAG_OFFLINE", default=False),
        )
        for name, field in (
            ("RAG_SOURCE", "source"),
            ("LLM_BASE_URL", "base_url"),
            ("LLM_MODEL", "llm_model"),
            ("EMBED_MODEL", "embed_model"),
        ):
            if value := os.getenv(name):
                settings = replace(settings, **{field: value})
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
        if self.offline:
            return "hash"
        model = self.embed_model.split("/")[-1].replace(":free", "")
        # "embeddinggemma" -> "embeddinggem": the common
        # prefix carries no information and the name has to stay short.
        model = re.sub(r"^text-embedding-", "", model)
        return re.sub(r"[^a-z0-9]+", "", model.lower())[:12]

    @property
    def use_server(self) -> bool:
        """Whether to call the model server at all.

        The local server needs no credentials, so this is a deliberate switch
        rather than "is a key present" — `RAG_OFFLINE=true` falls back to
        word-overlap vectors and disables generation.
        """
        return not self.offline
