"""Configuration for the whole pipeline, in one place.

Every stage takes its hyperparameters from here, and every optional stage has a
switch here that turns it off. Nothing is configured anywhere else: the CLI, the
Streamlit sidebar and the tests all build a `Settings` and hand it to the
pipeline, so what the UI shows is exactly what runs.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .llm import LOCAL_BASE_URL

DEFAULT_URL = (
    "https://ods.od.nih.gov/factsheets/"
    "ExerciseAndAthleticPerformance-HealthProfessional/"
)

# Loaded in LM Studio; `python -m rag.cli models` lists what the server offers.
EMBED_MODEL = "text-embedding-embeddinggemma-300m"
LLM_MODEL = "openai/gpt-oss-20b"

# EmbeddingGemma's own instruction templates. Measured on a creatine query
# against a matching and a mismatched passage, these separated the two by 0.47
# versus 0.35 with no prefixes — so they stay.
DOCUMENT_PREFIX = "title: none | text: "
QUERY_PREFIX = "task: search result | query: "

# Sections dropped whole by the cleaner — the 100+ entry reference list is the
# one that matters, and no query should ever retrieve it.
DROP_SECTIONS: Tuple[str, ...] = ("references", "disclaimer")

# Accepted values for `reasoning_effort`; "" leaves the field out of the request.
REASONING_EFFORTS: Tuple[str, ...] = ("", "low", "medium", "high")


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal `.env` reader — avoids a dependency for six lines of parsing.

    Existing environment variables always win, so `RAG_OFFLINE=true
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


def as_sections(value: Any) -> Tuple[str, ...]:
    """Normalise a section list: accepts a sequence or `"references, notes"`."""
    parts: Iterable[str] = (
        value.split(",") if isinstance(value, str) else (value or ())
    )
    return tuple(part.strip().lower() for part in parts if str(part).strip())


@dataclass
class Settings:
    """Everything tunable. `Settings.from_env()` is the normal entry point.

    Optional stages are switched off with the `enable_*` / `use_*` flags rather
    than by editing the pipeline: `enable_cleaning=False` chunks the raw
    extraction, `enable_questions=False` indexes chunks only, `enable_answers`
    drops the generation step, and `offline=True` skips the model server
    altogether.
    """

    # --- model server (LM Studio's local server, one endpoint for both) ------ #
    base_url: str = LOCAL_BASE_URL
    api_key: Optional[str] = None  # LM Studio needs none; hosted gateways do
    embed_model: str = EMBED_MODEL
    llm_model: str = LLM_MODEL
    embed_dimensions: int = 768  # what embeddinggemma-300m returns
    embed_batch_size: int = 16
    # Local models have no quota, so nothing is paced. Set this above 0 when
    # pointing `base_url` at a rate-limited hosted endpoint.
    requests_per_minute: int = 0
    # Local generation is slow — a reasoning model can spend half a minute on a
    # reply, and LM Studio may load the model on the first request.
    request_timeout: float = 300.0
    max_retries: int = 3
    # Passed through for servers that honour it; "" leaves it out of the request.
    reasoning_effort: str = ""
    # The embedding model is asymmetric — it was trained with these prefixes.
    # Set both to "" for a symmetric model.
    document_prefix: str = DOCUMENT_PREFIX
    query_prefix: str = QUERY_PREFIX
    # Skip the server entirely and use word-overlap vectors (RAG_OFFLINE).
    offline: bool = False

    # --- source / fetching -------------------------------------------------- #
    source: str = DEFAULT_URL
    source_url: str = DEFAULT_URL  # used to resolve relative links in local files
    cache_dir: Path = Path(".cache")
    use_cache: bool = True  # False re-extracts (and re-downloads) every time
    fetch_min_chars: int = 1_000  # below this, extraction silently lost content

    # --- cleaning (optional stage) ------------------------------------------ #
    # False hands the raw extraction straight to the chunker — worth trying once
    # to see what the cleaner is actually buying.
    enable_cleaning: bool = True
    strip_links: bool = True
    strip_citations: bool = True
    drop_boilerplate: bool = True
    name_empty_headings: bool = True
    drop_sections: Tuple[str, ...] = DROP_SECTIONS

    # --- chunking ----------------------------------------------------------- #
    chunk_size: int = 600
    chunk_overlap: int = 100
    min_chunk_chars: int = 80  # 0 keeps every fragment as its own chunk
    prepend_section: bool = True
    max_section_chars: int = 80  # cap on the heading path kept per chunk

    # --- augmentation (optional stage) -------------------------------------- #
    # The master switch, from RAG_ENABLE_QUESTIONS. When false, no questions are
    # generated or indexed no matter what `questions_per_chunk` says.
    enable_questions: bool = True
    questions_per_chunk: int = 3
    question_workers: int = 8  # concurrency above the rate limit buys nothing
    question_temperature: float = 0.3
    # Reasoning tokens come out of this budget too — too small and the reply
    # comes back empty.
    question_max_tokens: int = 1_024

    # --- storage ------------------------------------------------------------ #
    db_path: Path = Path("./chroma_db")
    collection_base: str = "ods_health_facts"
    index_batch_size: int = 100  # rows per upsert, so no single huge request

    # --- retrieval ---------------------------------------------------------- #
    top_k: int = 5
    dedupe_by_chunk: bool = True
    # How many extra rows to pull before collapsing duplicates. Only used when
    # `dedupe_by_chunk` is on: a chunk plus its questions can fill the top-k.
    retrieval_overfetch: int = 3

    # --- answering (optional stage) ----------------------------------------- #
    enable_answers: bool = True
    answer_temperature: float = 0.2
    answer_max_tokens: int = 2_048
    answer_max_context_chars: int = 8_000

    # --- diagnostics -------------------------------------------------------- #
    tiny_below: int = 100  # chunks under this are flagged TINY

    def __post_init__(self) -> None:
        # Callers (CLI flags, Streamlit widgets) pass plain strings.
        self.db_path = Path(self.db_path)
        self.cache_dir = Path(self.cache_dir)
        self.drop_sections = as_sections(self.drop_sections)
        if self.reasoning_effort not in REASONING_EFFORTS:
            self.reasoning_effort = ""
        # Collapsing the switch into the count here means everything downstream —
        # the pipeline, the collection name, the cost estimate — only has to look
        # at one number.
        if not self.enable_questions:
            self.questions_per_chunk = 0

    # -- construction -------------------------------------------------------- #
    @classmethod
    def from_env(cls, **overrides) -> "Settings":
        load_dotenv()
        settings = cls(
            api_key=os.getenv("LLM_API_KEY"),
            enable_questions=env_flag("RAG_ENABLE_QUESTIONS", default=True),
            enable_cleaning=env_flag("RAG_ENABLE_CLEANING", default=True),
            enable_answers=env_flag("RAG_ENABLE_ANSWERS", default=True),
            offline=env_flag("RAG_OFFLINE", default=False),
            use_cache=env_flag("RAG_USE_CACHE", default=True),
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

    # -- serialisation ------------------------------------------------------- #
    def to_dict(self) -> Dict[str, Any]:
        """JSON-friendly copy. The UI uses it as a cache key and displays it."""
        plain: Dict[str, Any] = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if isinstance(value, Path):
                value = str(value)
            elif isinstance(value, tuple):
                value = list(value)
            plain[field.name] = value
        return plain

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """Rebuild from `to_dict()`, ignoring keys this version does not know."""
        known = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> "Settings":
        return cls.from_dict(json.loads(text))

    def redacted(self) -> Dict[str, Any]:
        """`to_dict()` with the key masked — safe to show on screen."""
        data = self.to_dict()
        if data.get("api_key"):
            data["api_key"] = "***"
        return data

    def changed_from_defaults(self) -> Dict[str, Any]:
        """Fields that differ from the dataclass defaults, for a "what did I
        touch?" summary next to forty widgets."""
        reference = _reference()
        return {
            name: value
            for name, value in self.to_dict().items()
            if value != reference[name]
        }

    # -- identity ------------------------------------------------------------ #
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
            f"_s{int(self.prepend_section)}{self.index_variant}"
        )

    @property
    def index_variant(self) -> str:
        """Hash of the index-affecting settings the name has no room to spell out.

        Chroma caps collection names at 63 characters, and cleaning flags,
        heading caps and embedding prefixes all change the stored vectors. The
        suffix is empty while every one of them sits at its default, so
        collections built before these knobs existed keep their names.
        """
        # Compared through `to_dict()` so both sides are normalised the same
        # way — a tuple of sections and a list of the same sections are one
        # configuration, not two.
        plain, reference = self.to_dict(), _reference()
        current = {name: plain[name] for name in VARIANT_FIELDS}
        if all(current[name] == reference[name] for name in VARIANT_FIELDS):
            return ""
        digest = hashlib.sha1(repr(sorted(current.items())).encode("utf-8"))
        return f"_x{digest.hexdigest()[:6]}"

    @property
    def index_key(self) -> str:
        """Identity of the index and the connections that reach it.

        Two `Settings` sharing this key can share one `RAGPipeline`: everything
        else is pushed onto the live stages by `RAGPipeline.apply`, so moving a
        retrieval slider does not reopen the database.
        """
        return "|".join(
            str(part)
            for part in (
                self.collection_name, self.db_path, self.source, self.source_url,
                self.cache_dir, self.base_url, self.api_key, self.embed_model,
                self.embed_dimensions, self.offline,
            )
        )

    @property
    def reader_key(self) -> str:
        """Identity of `fetch | clean | chunk` — the free half of the pipeline.

        The UI caches chunks under it, so moving a retrieval or generation
        control does not throw away work that cannot have changed.
        """
        data = self.to_dict()
        return json.dumps({name: data[name] for name in READER_FIELDS}, sort_keys=True)

    @property
    def embedder_tag(self) -> str:
        """Short slug for the active embedder, for the collection name."""
        if self.offline:
            return "hash"
        model = self.embed_model.split("/")[-1].replace(":free", "")
        # "text-embedding-embeddinggemma-300m" -> "embeddinggem": the common
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


# Index-affecting settings that arrived after the collection naming scheme did.
# `index_variant` hashes them; see the note there for why they are not spelled
# out like the chunking parameters.
VARIANT_FIELDS: Tuple[str, ...] = (
    "enable_cleaning",
    "strip_links",
    "strip_citations",
    "drop_boilerplate",
    "name_empty_headings",
    "drop_sections",
    "max_section_chars",
    "document_prefix",
    "query_prefix",
)


# Everything `pipeline.reader()` reads. Nothing else can change the chunks.
READER_FIELDS: Tuple[str, ...] = (
    "source", "source_url", "cache_dir", "use_cache", "fetch_min_chars",
    "enable_cleaning", "strip_links", "strip_citations", "drop_boilerplate",
    "name_empty_headings", "drop_sections",
    "chunk_size", "chunk_overlap", "min_chunk_chars", "prepend_section",
    "max_section_chars",
)


@lru_cache(maxsize=1)
def _reference() -> Dict[str, Any]:
    """The all-defaults settings, as a dict — the baseline both comparisons use.

    Built through the constructor rather than read off `fields()` so that values
    `__post_init__` normalises (a `Path`, a section tuple) compare equal.
    """
    return Settings().to_dict()
