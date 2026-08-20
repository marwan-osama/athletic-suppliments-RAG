"""Streamlit UI for the athletic-supplements RAG pipeline.

Run with:  streamlit run app.py

The point of the UI is the feedback loop: change any stage's settings, see the
chunks that produced, ask questions, and judge the retrieved chunks.

The sidebar is one section per pipeline stage, in the order the stages run. Each
optional stage has a switch that bypasses it, and every hyperparameter that stage
takes is under that switch — there is nothing tunable in `Settings` that cannot
be reached from here.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

from evaluation import DiagnosticEngine, EvaluationEngine, ReportGenerator
from evaluation import available as evaluation_available
from evaluation import collect, load_dataset
from evaluation.evaluate_rag import METRIC_NAMES
from evaluation.evaluate_rag import INSTALL_HINT as EVAL_INSTALL_HINT
from evaluation.harness import HarnessError, check_ready
from rag.config import REASONING_EFFORTS, Settings
from rag.pipeline import RAGPipeline, reader
from rag.schema import Chunk, Retrieved

SEED_QUESTIONS = [
    "Does creatine improve athletic performance?",
    "How much beta-alanine is needed to improve exercise performance?",
    "Are there safety concerns with taking beetroot juice before exercise?",
    "Does caffeine help endurance athletes?",
]
VERDICTS = ["unjudged", "relevant", "not relevant"]

# Every settings widget is keyed with this prefix, which is what makes "Reset to
# defaults" a matter of dropping the keys and letting the `value=` defaults win.
CFG = "cfg-"

# Retry/failure messages from the pipeline. A plain deque rather than
# `st.session_state` because question generation logs from worker threads, and
# session state may only be touched from the main thread.
LOG: deque = deque(maxlen=200)

st.set_page_config(page_title="Athletic Supplements RAG", page_icon="🏃", layout="wide")


# --------------------------------------------------------------------------- #
# Cached pipeline pieces
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Fetching, cleaning and chunking…")
def load_chunks(reader_key: str, _settings: Settings) -> List[Chunk]:
    """Chunking only — no embeddings, so this is free to re-run on every move.

    Keyed on `reader_key`, which covers exactly the settings `reader()` reads;
    `_settings` is underscored so Streamlit passes it without hashing it.
    """
    return reader(_settings)(_settings.source)


@st.cache_resource(show_spinner="Opening the index…")
def get_pipeline(index_key: str, _settings: Settings) -> RAGPipeline:
    """One pipeline (and Chroma collection) per index configuration.

    `index_key` covers everything that decides what is stored in the index, so a
    cached pipeline can never be paired with vectors built from other settings.
    Everything else reaches the stages through `RAGPipeline.apply` instead, which
    is why moving a retrieval slider does not reopen the database.
    """
    return RAGPipeline(_settings, log=LOG.append)


def state(key: str, default):
    return st.session_state.setdefault(key, default)


def cfg(name: str) -> str:
    return f"{CFG}{name}"


def reset_config() -> None:
    """Drop every settings widget's state, so the defaults are shown again."""
    for key in [key for key in st.session_state if key.startswith(CFG)]:
        del st.session_state[key]


def switch(label: str, name: str, default: bool, help: str) -> bool:
    """The bypass switch for one optional stage, drawn above its settings."""
    return st.toggle(label, value=default, key=cfg(name), help=help)


def stage_title(icon: str, title: str, name: str, default: bool) -> str:
    """Expander label that says at a glance whether the stage is switched off."""
    on = st.session_state.get(cfg(name), default)
    return f"{icon} {title}" + ("" if on else " — bypassed")


# --------------------------------------------------------------------------- #
# Sidebar: one section per stage, in pipeline order
# --------------------------------------------------------------------------- #
def source_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("📥 Source & fetching"):
        values = {
            "source": st.text_input(
                "Source PDF", value=defaults.source, key=cfg("source"),
                help="Path to the PDF to index. Page numbers in citations are "
                     "this document's own pages.",
            ),
            "use_cache": switch(
                "Reuse the extracted markdown", "use_cache", defaults.use_cache,
                "Off re-runs PDF extraction every build.",
            ),
            "pdf_heading_levels": st.number_input(
                "Heading levels to recover", 0, 6,
                defaults.pdf_heading_levels, 1, key=cfg("pdf_heading_levels"),
                help="A PDF has no headings — this many distinct font sizes "
                     "above the body size become levels 1..N.",
            ),
            "pdf_drop_repeated_lines": switch(
                "Drop running heads and footers", "pdf_drop_repeated_lines",
                defaults.pdf_drop_repeated_lines,
                "Short lines that repeat in the top or bottom margin of most pages.",
            ),
            "cache_dir": st.text_input(
                "Cache directory", value=str(defaults.cache_dir), key=cfg("cache_dir")
            ),
            "fetch_min_chars": st.number_input(
                "Fail extraction below (chars)", 0, 200_000,
                defaults.fetch_min_chars, 100, key=cfg("fetch_min_chars"),
                help="A short extraction means content was silently lost.",
            ),
        }
    return values


def cleaning_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("🧹", "Cleaning", "enable_cleaning", defaults.enable_cleaning)
    ):
        enabled = switch(
            "Clean the markdown", "enable_cleaning", defaults.enable_cleaning,
            "Off hands the raw extraction to the chunker — link soup and all. "
            "Worth trying once to see what the cleaner is buying you.",
        )
        return {
            "enable_cleaning": enabled,
            "strip_links": st.checkbox(
                "Unwrap links", value=defaults.strip_links, key=cfg("strip_links"),
                disabled=not enabled, help="`[label](url)` becomes `label`.",
            ),
            "strip_citations": st.checkbox(
                "Drop citation markers", value=defaults.strip_citations,
                key=cfg("strip_citations"), disabled=not enabled,
                help="Removes `[112]`-style reference numbers.",
            ),
            "drop_boilerplate": st.checkbox(
                "Drop navigation lines", value=defaults.drop_boilerplate,
                key=cfg("drop_boilerplate"), disabled=not enabled,
                help="Short standalone lines like 'Ask ODS' or 'Back to top'.",
            ),
            "name_empty_headings": st.checkbox(
                "Name empty headings", value=defaults.name_empty_headings,
                key=cfg("name_empty_headings"), disabled=not enabled,
                help="A bare `###` is renamed after the first sentence below it, "
                     "so subsections still say which supplement they are about.",
            ),
            "drop_sections": st.text_input(
                "Drop these sections", value=", ".join(defaults.drop_sections),
                key=cfg("drop_sections"), disabled=not enabled,
                help="Comma-separated heading titles, dropped with their bodies.",
            ),
        }


def chunking_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("✂️ Chunking", expanded=True):
        chunk_size = st.slider(
            "Chunk size (chars)", 200, 2000, defaults.chunk_size, 50,
            key=cfg("chunk_size"),
        )
        overlap = st.slider(
            "Overlap (chars)", 0, 500, defaults.chunk_overlap, 25, key=cfg("chunk_overlap")
        )
        if overlap >= chunk_size:
            overlap = chunk_size // 4
            st.warning(f"Overlap must stay below chunk size — using {overlap}.")
        return {
            "chunk_size": chunk_size,
            "chunk_overlap": overlap,
            "min_chunk_chars": st.slider(
                "Merge fragments below (chars)", 0, 300, defaults.min_chunk_chars, 10,
                key=cfg("min_chunk_chars"),
                help="0 keeps every fragment as a chunk of its own.",
            ),
            "prepend_section": st.checkbox(
                "Prefix chunks with their heading path",
                value=defaults.prepend_section, key=cfg("prepend_section"),
                help="Turns '#### Efficacy' into 'Creatine > Efficacy' inside "
                     "the chunk text.",
            ),
            "max_section_chars": st.slider(
                "Heading path cap (chars)", 20, 200, defaults.max_section_chars, 10,
                key=cfg("max_section_chars"),
                help="Outer heading levels are dropped until the path fits.",
            ),
        }


def question_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("❓", "Question augmentation", "enable_questions",
                    defaults.enable_questions)
    ):
        enabled = switch(
            "Generate hypothetical questions", "enable_questions",
            defaults.enable_questions,
            "Indexed alongside each chunk so user-style questions have something "
            "question-shaped to match. Costs one local generation call per "
            "chunk, which is the slow half of a build.",
        )
        return {
            "enable_questions": enabled,
            "questions_per_chunk": st.slider(
                "Questions per chunk", 1, 10,
                # The count is zeroed while the switch is off, so fall back to
                # the default rather than showing a slider pinned at its floor.
                defaults.questions_per_chunk or Settings.questions_per_chunk, 1,
                key=cfg("questions_per_chunk"), disabled=not enabled,
            ),
            "question_workers": st.slider(
                "Worker threads", 1, 32, defaults.question_workers, 1,
                key=cfg("question_workers"), disabled=not enabled,
                help="Concurrency above the rate limit buys nothing.",
            ),
            "question_temperature": st.slider(
                "Temperature", 0.0, 2.0, float(defaults.question_temperature), 0.05,
                key=cfg("question_temperature"), disabled=not enabled,
            ),
            "question_max_tokens": st.number_input(
                "Max tokens per call", 64, 32_768, defaults.question_max_tokens, 64,
                key=cfg("question_max_tokens"), disabled=not enabled,
                help="Reasoning tokens come out of this budget too — too small "
                     "and the reply comes back empty.",
            ),
        }


def embedding_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("🔢", "Embedding", "use_server", defaults.use_server)
    ):
        offline = not switch(
            "Use the model server", "use_server", defaults.use_server,
            "Off falls back to offline word-overlap vectors: no server needed, "
            "and no generation either. Retrieval quality drops a long way.",
        )
        return {
            "offline": offline,
            "embed_model": st.text_input(
                "Embedding model", value=defaults.embed_model, key=cfg("embed_model"),
                disabled=offline,
            ),
            "embed_batch_size": st.slider(
                "Texts per embedding call", 1, 128, defaults.embed_batch_size, 1,
                key=cfg("embed_batch_size"), disabled=offline,
            ),
            "embed_dimensions": st.number_input(
                "Reported dimensions", 1, 8192, defaults.embed_dimensions, 1,
                key=cfg("embed_dimensions"), disabled=offline,
                help="What the model returns. Shown on the Index tab; the "
                     "server decides the real width.",
            ),
            "document_prefix": st.text_input(
                "Document prefix", value=defaults.document_prefix,
                key=cfg("document_prefix"), disabled=offline,
                help="This embedder is asymmetric — it was trained with an "
                     "instruction on each side. Empty for a symmetric model.",
            ),
            "query_prefix": st.text_input(
                "Query prefix", value=defaults.query_prefix, key=cfg("query_prefix"),
                disabled=offline,
            ),
        }


def storage_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("🗄️ Index storage"):
        return {
            "db_path": st.text_input(
                "Chroma path", value=str(defaults.db_path), key=cfg("db_path")
            ),
            "collection_base": st.text_input(
                "Collection prefix", value=defaults.collection_base,
                key=cfg("collection_base"),
                help="The rest of the name is derived from the settings that "
                     "decide what the vectors contain.",
            ),
            "index_batch_size": st.slider(
                "Rows per upsert", 1, 1000, defaults.index_batch_size, 10,
                key=cfg("index_batch_size"),
            ),
        }


def expansion_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("🔀", "Query expansion", "enable_query_expansion",
                    defaults.enable_query_expansion)
    ):
        enabled = switch(
            "Search other phrasings too", "enable_query_expansion",
            defaults.enable_query_expansion,
            "Asks the model for alternative wordings of the question and "
            "searches for each. Finds passages worded differently from the "
            "query, at one generation call per search — so searching gets "
            "slower, not building.",
        )
        return {
            "enable_query_expansion": enabled,
            "query_expansions": st.slider(
                "Extra phrasings", 1, 8,
                # Zeroed while the switch is off, so fall back to the default
                # rather than showing a slider pinned at its floor.
                defaults.query_expansions or Settings.query_expansions, 1,
                key=cfg("query_expansions"), disabled=not enabled,
                help="Each one costs a search of its own; the original query is "
                     "always kept.",
            ),
            "query_expansion_temperature": st.slider(
                "Temperature", 0.0, 2.0,
                float(defaults.query_expansion_temperature), 0.05,
                key=cfg("query_expansion_temperature"), disabled=not enabled,
                help="Higher than the other stages by default: phrasings that "
                     "differ from each other are the point.",
            ),
            "query_expansion_max_tokens": st.number_input(
                "Max tokens per call", 32, 8_192,
                defaults.query_expansion_max_tokens, 32,
                key=cfg("query_expansion_max_tokens"), disabled=not enabled,
            ),
            "match_boost": st.slider(
                "Agreement boost", 0.0, 0.3, float(defaults.match_boost), 0.01,
                key=cfg("match_boost"), disabled=not enabled,
                help="Added to a chunk's rank for each phrasing beyond the "
                     "first that found it. Moves the ranking only — the "
                     "similarity shown on a result is never touched.",
            ),
            "match_boost_cap": st.slider(
                "Boost cap", 0.0, 0.5, float(defaults.match_boost_cap), 0.01,
                key=cfg("match_boost_cap"), disabled=not enabled,
                help="However many phrasings agree, the boost stops here.",
            ),
        }


def rerank_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("🎯", "Reranking", "enable_rerank", defaults.enable_rerank)
    ):
        enabled = switch(
            "Let the model reorder results", "enable_rerank",
            defaults.enable_rerank,
            "Pulls a longer candidate list, has the model rank it against the "
            "question, then keeps top-k. The embedder scores question and "
            "passage separately; the reranker reads them together. One "
            "generation call per search.",
        )
        return {
            "enable_rerank": enabled,
            "rerank_candidates": st.slider(
                "Candidates to rank", 0, 50, defaults.rerank_candidates, 5,
                key=cfg("rerank_candidates"), disabled=not enabled,
                help="Fetched before the cut to top-k. On this corpus 41% of the "
                     "useful passages sit between ranks 6 and 20, which is what "
                     "a deeper pool recovers.",
            ),
            "rerank_temperature": st.slider(
                "Temperature", 0.0, 1.0, float(defaults.rerank_temperature), 0.05,
                key=cfg("rerank_temperature"), disabled=not enabled,
                help="0 by default: an ordering should not move between runs.",
            ),
            "rerank_snippet_chars": st.number_input(
                "Chars per candidate", 100, 2_000,
                defaults.rerank_snippet_chars, 50,
                key=cfg("rerank_snippet_chars"), disabled=not enabled,
                help="How much of each chunk the ranker sees. Keeps the prompt "
                     "tight when the candidate list is long.",
            ),
            "rerank_max_tokens": st.number_input(
                "Max tokens per call", 32, 8_192, defaults.rerank_max_tokens, 32,
                key=cfg("rerank_max_tokens"), disabled=not enabled,
            ),
        }


def retrieval_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("🔎 Retrieval", expanded=True):
        dedupe = st.checkbox(
            "One result per chunk", value=defaults.dedupe_by_chunk,
            key=cfg("dedupe_by_chunk"),
            help="Collapse a chunk and its hypothetical questions into a single "
                 "result. Off lets one passage fill the whole top-k.",
        )
        return {
            "top_k": st.slider("Top-k results", 1, 20, defaults.top_k, 1, key=cfg("top_k")),
            "dedupe_by_chunk": dedupe,
            "retrieval_overfetch": st.slider(
                "Overfetch multiplier", 1, 10, defaults.retrieval_overfetch, 1,
                key=cfg("retrieval_overfetch"), disabled=not dedupe,
                help="How many rows to pull per requested result before "
                     "collapsing duplicates.",
            ),
        }


def answering_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander(
        stage_title("💬", "Answering", "enable_answers", defaults.enable_answers)
    ):
        enabled = switch(
            "Compose answers from the sources", "enable_answers",
            defaults.enable_answers,
            "Optional: retrieval quality is judged from the chunks themselves, "
            "and this costs an extra generation call.",
        )
        return {
            "enable_answers": enabled,
            "answer_temperature": st.slider(
                "Temperature", 0.0, 2.0, float(defaults.answer_temperature), 0.05,
                key=cfg("answer_temperature"), disabled=not enabled,
            ),
            "answer_max_tokens": st.number_input(
                "Max tokens", 64, 32_768, defaults.answer_max_tokens, 64,
                key=cfg("answer_max_tokens"), disabled=not enabled,
                help="Generous by default: this model's reasoning comes out of "
                     "the same budget as the answer.",
            ),
            "answer_max_context_chars": st.number_input(
                "Context budget (chars)", 500, 200_000,
                defaults.answer_max_context_chars, 500,
                key=cfg("answer_max_context_chars"), disabled=not enabled,
                help="Sources are truncated to fit; later ones drop out first.",
            ),
        }


def server_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("🔌 Model server"):
        return {
            "base_url": st.text_input(
                "Base URL", value=defaults.base_url, key=cfg("base_url"),
                help="Anything that speaks the OpenAI shape: LM Studio locally, "
                     "or a hosted gateway.",
            ),
            "llm_model": st.text_input(
                "Generation model", value=defaults.llm_model, key=cfg("llm_model"),
                help="Used for both hypothetical questions and answers.",
            ),
            "api_key": st.text_input(
                "API key", value=defaults.api_key or "", type="password",
                key=cfg("api_key"),
                help="LM Studio needs none. Defaults to LLM_API_KEY from .env.",
            ) or None,
            "embed_base_url": st.text_input(
                "Embeddings base URL", value=defaults.embed_base_url,
                key=cfg("embed_base_url"),
                help="Blank uses the base URL above. Set it when generation is "
                     "hosted and embeddings are not — OpenRouter, for one, "
                     "serves no /embeddings.",
            ),
            "embed_api_key": st.text_input(
                "Embeddings API key", value=defaults.embed_api_key or "",
                type="password", key=cfg("embed_api_key"),
                help="Blank reuses the key above. Defaults to EMBED_API_KEY.",
            ) or None,
            "requests_per_minute": st.number_input(
                "Rate limit (requests/min)", 0, 10_000, defaults.requests_per_minute, 10,
                key=cfg("requests_per_minute"), help="0 disables pacing.",
            ),
            "request_timeout": st.number_input(
                "Request timeout (s)", 5.0, 3600.0, float(defaults.request_timeout), 5.0,
                key=cfg("request_timeout"),
                help="Local generation is slow, and the first request may load "
                     "the model.",
            ),
            "max_retries": st.slider(
                "Max retries", 1, 10, defaults.max_retries, 1, key=cfg("max_retries"),
                help="Applies to timeouts, 429s and 5xx. A 400 is never retried.",
            ),
            "reasoning_effort": st.selectbox(
                "Reasoning effort", REASONING_EFFORTS,
                index=REASONING_EFFORTS.index(defaults.reasoning_effort),
                format_func=lambda value: value or "leave unset",
                key=cfg("reasoning_effort"),
                help="Passed through for servers that honour it. The local "
                     "build reasons regardless; a hosted one may not.",
            ),
            "llm_extra_body": st.text_area(
                "Extra request body (JSON)", value=defaults.llm_extra_body,
                key=cfg("llm_extra_body"), height=68,
                placeholder='{"provider": {"quantizations": ["fp4"]}}',
                help="Merged into every chat request, for fields outside the "
                     "OpenAI shape — a gateway's routing preferences, for "
                     "instance. Which provider answers changes how much the "
                     "model reasons, so pin it when runs must be comparable.",
            ),
        }


def evaluation_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("📊 Evaluation"):
        st.caption(
            "Grades the pipeline on the Evaluate tab. Runs on demand — none of "
            "this affects a search."
        )
        return {
            "eval_dataset_path": st.text_input(
                "Golden set", value=str(defaults.eval_dataset_path),
                key=cfg("eval_dataset_path"),
                help="A .json, .jsonl or .csv of questions and reference "
                     "answers. Contexts and answers come from the pipeline.",
            ),
            "eval_output_dir": st.text_input(
                "Report directory", value=str(defaults.eval_output_dir),
                key=cfg("eval_output_dir"),
            ),
            "eval_threshold": st.slider(
                "Failure threshold", 0.0, 1.0, float(defaults.eval_threshold), 0.05,
                key=cfg("eval_threshold"),
                help="A metric below this counts as a failure and gets diagnosed.",
            ),
            "eval_llm_model": st.text_input(
                "Judge model", value=defaults.eval_llm_model,
                key=cfg("eval_llm_model"),
                placeholder=defaults.llm_model,
                help="Blank uses the generation model. A stronger judge than "
                     "the model being judged is the usual arrangement.",
            ),
            "eval_embed_model": st.text_input(
                "Judge embeddings", value=defaults.eval_embed_model,
                key=cfg("eval_embed_model"), placeholder=defaults.embed_model,
                help="Blank uses the pipeline's embedding model. Answer "
                     "relevancy is the metric that needs it.",
            ),
            "eval_embed_base_url": st.text_input(
                "Judge embeddings endpoint", value=defaults.eval_embed_base_url,
                key=cfg("eval_embed_base_url"),
                placeholder=defaults.embed_endpoint()[0],
                help="Blank uses the pipeline's embedding endpoint — not the "
                     "judge endpoint below, which may be a gateway that serves "
                     "no embeddings at all.",
            ),
            "eval_base_url": st.text_input(
                "Judge endpoint", value=defaults.eval_base_url,
                key=cfg("eval_base_url"), placeholder=defaults.base_url,
                help="Blank uses the same server. Point it elsewhere to judge "
                     "local answers with a hosted model.",
            ),
            "eval_normalize_acronyms": st.checkbox(
                "Expand medical acronyms", value=defaults.eval_normalize_acronyms,
                key=cfg("eval_normalize_acronyms"),
                help="So 'HMB' and 'beta-hydroxy beta-methylbutyrate' are not "
                     "scored as different claims.",
            ),
            "eval_llm_diagnostics": st.checkbox(
                "Diagnose failures with the model", value=defaults.eval_llm_diagnostics,
                key=cfg("eval_llm_diagnostics"),
                help="Adds a written analysis per failing sample, at one "
                     "generation call each. Off leaves the rule-based advice.",
            ),
            "eval_max_workers": st.slider(
                "Judge concurrency", 1, 16, defaults.eval_max_workers, 1,
                key=cfg("eval_max_workers"),
                help="One at a time by default — a local model serving several "
                     "scoring calls at once mostly queues them.",
            ),
            "eval_timeout": st.number_input(
                "Judge timeout (s)", 10, 3600, defaults.eval_timeout, 10,
                key=cfg("eval_timeout"),
            ),
        }


def diagnostics_controls(defaults: Settings) -> Dict[str, Any]:
    with st.sidebar.expander("🩺 Chunk diagnostics"):
        return {
            "tiny_below": st.slider(
                "Flag chunks below (chars)", 0, 500, defaults.tiny_below, 10,
                key=cfg("tiny_below"),
                help="Only affects the TINY flag on the Chunks tab, not the "
                     "chunking itself.",
            ),
        }


def sidebar() -> Settings:
    defaults = Settings.from_env()
    st.sidebar.title("🏃 Pipeline settings")
    st.sidebar.caption(
        "One section per stage, in the order they run. Optional stages have a "
        "switch that bypasses them."
    )

    values: Dict[str, Any] = {}
    for controls in (
        source_controls, cleaning_controls, chunking_controls, question_controls,
        embedding_controls, storage_controls, expansion_controls,
        retrieval_controls, rerank_controls, answering_controls, server_controls,
        diagnostics_controls, evaluation_controls,
    ):
        values.update(controls(defaults))
    return defaults.with_(**values)


# --------------------------------------------------------------------------- #
# Sidebar: index status and building
# --------------------------------------------------------------------------- #
def sidebar_status(pipeline: RAGPipeline, settings: Settings) -> None:
    st.sidebar.subheader("Index")
    st.sidebar.caption(f"Collection `{settings.collection_name}`")
    st.sidebar.metric("Rows indexed", f"{pipeline.index.count:,}")

    if pipeline.offline:
        st.sidebar.warning(
            "The model server is switched off — running on offline hash "
            "embeddings. Retrieval quality will be poor, and nothing is "
            "generated. Turn it back on under **Embedding**."
        )

    build, reset = st.sidebar.columns(2)
    if build.button("Build index", type="primary", use_container_width=True):
        run_build(pipeline, force=False)
    if reset.button("Rebuild", use_container_width=True,
                    help="Delete this collection and index again from scratch"):
        run_build(pipeline, force=True)

    changed = settings.changed_from_defaults()
    st.sidebar.button(
        f"Reset {len(changed)} changed setting{'s' if len(changed) != 1 else ''}",
        on_click=reset_config, use_container_width=True, disabled=not changed,
    )
    st.sidebar.caption(
        "Settings that change the stored vectors switch you to a collection of "
        "their own, so you can compare configurations without wiping anything."
    )


def run_build(pipeline: RAGPipeline, force: bool) -> None:
    bar = st.sidebar.progress(0.0, text="starting…")

    def on_progress(label: str, done: int, total: int) -> None:
        bar.progress(done / max(total, 1), text=f"{label}: {done}/{total}")

    try:
        report = pipeline.build(force=force, on_progress=on_progress)
    except Exception as exc:  # noqa: BLE001 - surface API/parsing errors in the UI
        bar.empty()
        st.sidebar.error(f"Build failed: {exc}")
        return

    bar.empty()
    st.sidebar.success(report.summary())
    if report.skipped:
        st.sidebar.caption("Use **Rebuild** to re-index with the current settings.")


# --------------------------------------------------------------------------- #
# Tab: ask
# --------------------------------------------------------------------------- #
def ask_tab(pipeline: RAGPipeline, settings: Settings) -> None:
    questions: List[str] = state("questions", list(SEED_QUESTIONS))

    with st.form("ask", clear_on_submit=True):
        typed = st.text_input("Ask a question", placeholder="e.g. Is HMB safe?")
        search, add = st.columns([1, 1])
        submitted = search.form_submit_button("Search", type="primary", use_container_width=True)
        saved = add.form_submit_button("Add to question set", use_container_width=True)

    if saved and typed.strip():
        if typed.strip() not in questions:
            questions.append(typed.strip())
        st.toast(f"Added: {typed.strip()}")
    if submitted and typed.strip():
        run_search(pipeline, typed.strip(), settings.top_k)

    with st.expander(f"Question set ({len(questions)})", expanded=not state("results", {})):
        for position, question in enumerate(questions):
            row = st.columns([8, 1, 1])
            row[0].markdown(f"`{position + 1}.` {question}")
            if row[1].button("Search", key=f"run-{position}", use_container_width=True):
                run_search(pipeline, question, settings.top_k)
            if row[2].button("✕", key=f"del-{position}", use_container_width=True):
                questions.pop(position)
                st.rerun()
        if questions and st.button(f"Search all {len(questions)} questions"):
            for question in questions:
                run_search(pipeline, question, settings.top_k, rerun=False)
            st.rerun()

    results: Dict[str, List[Retrieved]] = state("results", {})
    if not results:
        st.info("Build the index in the sidebar, then ask a question.")
        return

    for question in reversed(list(results)):
        render_results(pipeline, question, results[question])


def run_search(pipeline: RAGPipeline, question: str, top_k: int, rerun: bool = True) -> None:
    if pipeline.index.count == 0:
        st.warning("The index is empty — build it first.")
        return
    try:
        state("results", {})[question] = pipeline.search(question, top_k=top_k)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Search failed: {exc}")
        return
    if rerun:
        st.rerun()


def render_results(pipeline: RAGPipeline, question: str, hits: List[Retrieved]) -> None:
    st.markdown(f"### {question}")
    judged = reviews_for(question)
    relevant = sum(value["verdict"] == "relevant" for value in judged.values())
    header = st.columns([2, 2, 2, 3])
    header[0].metric("Results", len(hits))
    header[1].metric("Top similarity", f"{hits[0].similarity:.3f}" if hits else "—")
    header[2].metric("Judged relevant", f"{relevant}/{len(hits)}")
    if header[3].button(
        "Generate answer", key=f"answer-{question}",
        disabled=not pipeline.can_answer, use_container_width=True,
        help=None if pipeline.can_answer else
             "Switch Answering on in the sidebar (and the model server with it).",
    ):
        with st.spinner("Answering…"):
            state("answers", {})[question] = pipeline.answer(question, hits)

    if answer := state("answers", {}).get(question):
        st.success(answer)

    for position, hit in enumerate(hits, start=1):
        render_hit(question, position, hit)
    st.divider()


def render_hit(question: str, position: int, hit: Retrieved) -> None:
    badge = "❓ question match" if hit.match_type == "question" else "📄 chunk match"
    agreement = (
        f" · 🔀 {hit.matches} phrasings agreed, rank +{hit.boost:.2f}"
        if hit.matches > 1 else ""
    )
    where = f" · 📄 {hit.pages_label}" if hit.pages_label else ""
    if hit.rerank_move > 0:
        moved = f" · 🎯 up {hit.rerank_move} from #{hit.dense_rank}"
    elif hit.rerank_move < 0:
        moved = f" · 🎯 down {-hit.rerank_move} from #{hit.dense_rank}"
    else:
        moved = ""
    title = (
        f"**{position}. {hit.section or 'document'}**{where} — similarity "
        f"{hit.similarity:.3f} · {badge} · {len(hit.text)} chars{agreement}{moved}"
    )
    with st.expander(title, expanded=position <= 3):
        st.progress(max(0.0, min(hit.similarity, 1.0)))
        if hit.matched_text:
            st.caption(f"Matched this generated question: *{hit.matched_text}*")
        # st.code, not st.markdown: the chunk is shown exactly as it was indexed.
        st.code(hit.text, language=None, wrap_lines=True)

        key = f"{question}||{hit.chunk_id}"
        review = state("reviews", {}).get(key, {"verdict": "unjudged", "note": ""})
        columns = st.columns([3, 5])
        verdict = columns[0].radio(
            "Relevant to the question?", VERDICTS,
            index=VERDICTS.index(review["verdict"]), horizontal=False, key=f"v-{key}",
        )
        note = columns[1].text_input("Note (optional)", value=review["note"], key=f"n-{key}")
        state("reviews", {})[key] = {
            "verdict": verdict,
            "note": note,
            "question": question,
            "chunk_id": hit.chunk_id,
            "section": hit.section,
            "pages": hit.pages_label,
            "similarity": round(hit.similarity, 4),
            "score": round(hit.score, 4),
            "matches": hit.matches,
            "match_type": hit.match_type,
            "dense_rank": hit.dense_rank,
            "rank": position,
        }
        st.caption(f"chunk `{hit.chunk_id}` · index {hit.chunk_index}")


def reviews_for(question: str) -> Dict[str, dict]:
    return {
        key: value
        for key, value in state("reviews", {}).items()
        if value.get("question") == question
    }


# --------------------------------------------------------------------------- #
# Tab: chunks
# --------------------------------------------------------------------------- #
def chunks_tab(pipeline: RAGPipeline, settings: Settings) -> None:
    try:
        chunks = load_chunks(settings.reader_key, settings)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read the source: {exc}")
        return

    report = pipeline.inspect(chunks)
    columns = st.columns(5)
    columns[0].metric("Chunks", report.total)
    columns[1].metric("Sections", report.sections)
    columns[2].metric("Median chars", f"{report.median_chars:.0f}")
    columns[3].metric("Max chars", report.max_chars)
    columns[4].metric("Flagged", len(report.flags))
    estimate = pipeline.estimate_build(report.total)
    st.caption(
        f"Rows this configuration would index: {report.total} chunks + up to "
        f"{report.total * settings.questions_per_chunk} questions = "
        f"**{report.total * (1 + settings.questions_per_chunk)}** embeddings — "
        f"{estimate.embedding_calls} embedding calls and "
        f"{estimate.generation_calls} generation calls, roughly "
        f"**{estimate.minutes:.0f} min** locally."
    )
    if not settings.enable_cleaning:
        st.warning(
            "Cleaning is bypassed — these chunks are the raw extraction, "
            "citation markers and navigation included."
        )

    only_flagged = st.toggle("Show only flagged chunks", value=False)
    needle = st.text_input("Filter by text or section", placeholder="creatine")

    shown = [
        chunk for chunk in chunks
        if (not only_flagged or chunk.index in report.flags)
        and (not needle or needle.lower() in chunk.text.lower())
    ]
    st.write(f"Showing **{len(shown)}** of {report.total} chunks")

    st.download_button(
        "Download all chunks (.md)",
        data="".join(
            f"\n{'=' * 70}\n[{c.index}] {c.size} chars "
            f"{' '.join(report.flags.get(c.index, [])) or 'ok'}\n"
            f"section: {c.section or '-'}  |  {c.pages_label or '-'}\n"
            f"{'=' * 70}\n{c.text}\n"
            for c in chunks
        ),
        file_name=f"chunks_c{settings.chunk_size}_o{settings.chunk_overlap}.md",
    )

    for chunk in shown[:200]:
        flags = " ".join(report.flags.get(chunk.index, [])) or "ok"
        with st.expander(f"**[{chunk.index}]** {chunk.section or 'document'} · "
                         f"{chunk.pages_label} — {chunk.size} chars · {flags}"):
            st.code(chunk.text, language=None, wrap_lines=True)
    if len(shown) > 200:
        st.caption("Showing the first 200 matches — narrow the filter to see more.")


# --------------------------------------------------------------------------- #
# Tab: review
# --------------------------------------------------------------------------- #
def review_tab() -> None:
    reviews = state("reviews", {})
    judged = [value for value in reviews.values() if value["verdict"] != "unjudged"]
    if not judged:
        st.info("Judge some retrieved chunks in the **Ask** tab and they appear here.")
        return

    relevant = [value for value in judged if value["verdict"] == "relevant"]
    columns = st.columns(3)
    columns[0].metric("Chunks judged", len(judged))
    columns[1].metric("Marked relevant", len(relevant))
    columns[2].metric("Precision", f"{len(relevant) / len(judged):.0%}")

    per_question: Dict[str, List[dict]] = {}
    for value in judged:
        per_question.setdefault(value["question"], []).append(value)

    st.dataframe(
        [
            {
                "question": question,
                "judged": len(values),
                "relevant": sum(v["verdict"] == "relevant" for v in values),
                "best rank hit": min(
                    (v["rank"] for v in values if v["verdict"] == "relevant"), default=None
                ),
                "mean similarity": round(
                    sum(v["similarity"] for v in values) / len(values), 4
                ),
            }
            for question, values in per_question.items()
        ],
        use_container_width=True,
    )

    st.dataframe(sorted(judged, key=lambda v: (v["question"], v["rank"])),
                 use_container_width=True)
    st.download_button(
        "Download judgements (.json)",
        data=json.dumps(judged, indent=2),
        file_name="retrieval_review.json",
        mime="application/json",
    )
    if st.button("Clear all judgements"):
        reviews.clear()
        st.rerun()


# --------------------------------------------------------------------------- #
# Tab: evaluate
# --------------------------------------------------------------------------- #
def evaluate_tab(pipeline: RAGPipeline, settings: Settings) -> None:
    st.caption(
        "Asks the pipeline every question in the golden set and grades what "
        "comes back, so these numbers move when the settings above do."
    )

    try:
        dataset = load_dataset(settings.eval_dataset_path)
    except Exception as exc:  # noqa: BLE001 - a missing or malformed file
        st.error(f"Could not read the golden set: {exc}")
        return

    base_url, judge, judge_embed = settings.eval_endpoint()
    columns = st.columns(4)
    columns[0].metric("Questions", len(dataset))
    columns[1].metric("Threshold", f"{settings.eval_threshold:.2f}")
    columns[2].metric("Judge", judge.split("/")[-1])
    columns[3].metric("Rows indexed", f"{pipeline.index.count:,}")
    st.caption(f"Judge `{judge}` · embeddings `{judge_embed}` · at `{base_url}`")

    blocked = evaluation_blocker(pipeline)
    if blocked:
        st.warning(blocked)
    if st.button("Run evaluation", type="primary", disabled=bool(blocked),
                 help="One search and one answer per question, then the judge "
                      "reads every sample — minutes, not seconds."):
        run_evaluation(pipeline, settings, dataset)

    result = state("eval", {}).get("result")
    if result is None:
        with st.expander(f"Golden set ({len(dataset)} questions)"):
            for position, row in enumerate(dataset, start=1):
                st.markdown(f"`{position}.` **{row['question']}**")
                st.caption(row["ground_truth"])
        return

    render_evaluation(result, state("eval", {}).get("diagnostics"),
                      state("eval", {}).get("report_path"))


def evaluation_blocker(pipeline: RAGPipeline) -> str:
    """Why the run would be meaningless, in the order the user can fix it."""
    if not evaluation_available():
        return EVAL_INSTALL_HINT
    try:
        check_ready(pipeline)
    except HarnessError as exc:
        return str(exc)
    return ""


def run_evaluation(pipeline: RAGPipeline, settings: Settings, dataset) -> None:
    bar = st.progress(0.0, text="asking the pipeline…")
    try:
        records = collect(
            pipeline, dataset,
            on_progress=lambda done, total: bar.progress(
                done / max(total, 1), text=f"asking the pipeline: {done}/{total}"
            ),
        )
        bar.progress(1.0, text="scoring — the judge reads every sample…")
        result = EvaluationEngine(settings).run(records)
        diagnostics = DiagnosticEngine(settings).run(result)
    except Exception as exc:  # noqa: BLE001 - surface judge/server errors in the UI
        bar.empty()
        st.error(f"Evaluation failed: {exc}")
        return

    bar.empty()
    path = ReportGenerator(settings.eval_output_dir).save_json(result, diagnostics)
    state("eval", {}).update(result=result, diagnostics=diagnostics, report_path=path)
    st.rerun()


def render_evaluation(result, diagnostics, report_path) -> None:
    st.subheader("Scores")
    columns = st.columns(len(result.aggregate))
    for column, (metric, score) in zip(columns, result.aggregate.items()):
        column.metric(
            metric.replace("_", " ").title(), f"{score:.3f}",
            delta=f"{score - result.threshold:+.3f} vs threshold",
            delta_color="normal" if score >= result.threshold else "inverse",
        )
    st.caption(
        "Recall and precision grade retrieval; faithfulness and relevancy "
        "grade the answer — so a failing metric names the stage to look at."
    )

    st.dataframe(
        [
            {
                "question": sample.question,
                **{name: round(sample.scores[name], 3) for name in METRIC_NAMES},
                "failing": ", ".join(sample.failing_stages) or "—",
            }
            for sample in result.samples
        ],
        use_container_width=True,
    )

    if report_path:
        st.caption(f"Report written to `{report_path}`")
        st.download_button(
            "Download report (.json)",
            data=Path(report_path).read_text(encoding="utf-8"),
            file_name=Path(report_path).name,
            mime="application/json",
        )

    if diagnostics and diagnostics.prioritised_actions:
        st.subheader("What to try, most failures first")
        for action in diagnostics.prioritised_actions[:8]:
            st.markdown(f"- {action}")

    for sample in result.samples:
        if not sample.failure_flags:
            continue
        with st.expander(
            f"❌ {sample.question} — {', '.join(sample.failure_flags)}"
        ):
            st.markdown("**Answer**")
            st.info(sample.answer)
            st.markdown("**Reference**")
            st.caption(sample.ground_truth)
            if sample.retrieved:
                st.markdown("**Retrieved**")
                st.dataframe(sample.retrieved, use_container_width=True)
            analysis = next(
                (d.llm_analysis for d in (diagnostics.diagnoses if diagnostics else [])
                 if d.question == sample.question and d.llm_analysis),
                "",
            )
            if analysis:
                st.markdown("**Diagnosis**")
                st.write(analysis)


# --------------------------------------------------------------------------- #
# Tab: index
# --------------------------------------------------------------------------- #
def index_tab(pipeline: RAGPipeline, settings: Settings) -> None:
    columns = st.columns(3)
    columns[0].metric("Rows in collection", f"{pipeline.index.count:,}")
    columns[1].metric("Embedding model",
                      "hash (offline)" if pipeline.offline
                      else settings.embed_model.split("/")[-1])
    columns[2].metric("Dimensions", pipeline.embedder.dimensions)

    st.caption(f"Chroma path `{settings.db_path}` · collection "
               f"`{settings.collection_name}`")
    if not pipeline.offline:
        st.caption(
            f"Embeddings `{settings.embed_model}` · generation "
            f"`{settings.llm_model}` · served from `{settings.base_url}`"
        )
        try:
            st.caption(f"Models loaded on the server: {pipeline.client.models()}")
        except Exception as exc:  # noqa: BLE001 - the server may simply be off
            st.warning(f"Model server not reachable: {exc}")

    if pipeline.index.count:
        st.write("Row types:", pipeline.index.stats())

    st.subheader("Stages in force")
    st.write(
        {
            "reading": repr(pipeline.reader),
            "questions": (
                f"{settings.questions_per_chunk} per chunk · {settings.llm_model} "
                f"· {settings.question_workers} workers"
                if pipeline.generator else "bypassed"
            ),
            "expansion": (
                f"{settings.query_expansions} extra phrasings · "
                f"{settings.llm_model} · temperature "
                f"{settings.query_expansion_temperature}"
                if pipeline.can_expand else "bypassed"
            ),
            "retrieval": (
                f"top {settings.top_k}"
                + (f" · collapsed from {settings.top_k * settings.retrieval_overfetch}"
                   if settings.dedupe_by_chunk else " · duplicates kept")
            ),
            "answering": (
                f"{settings.llm_model} · temperature {settings.answer_temperature}"
                if pipeline.can_answer else "bypassed"
            ),
        }
    )

    st.subheader("Collections on disk")
    st.write(pipeline.index.collections() or "none yet")
    st.caption(
        "Each indexing configuration gets its own collection, so switching the "
        "sidebar back to a previous setting reuses the index you already built."
    )

    st.subheader("Effective settings")
    changed = redacted_changes(settings)
    st.caption(
        f"{len(changed)} of {len(settings.to_dict())} settings differ from the "
        "defaults." if changed else "Every setting is at its default."
    )
    if changed:
        st.json(changed)
    with st.expander("All settings"):
        st.json(settings.redacted())

    if LOG:
        st.subheader("Pipeline log")
        st.code("\n".join(LOG))


def redacted_changes(settings: Settings) -> Dict[str, Any]:
    changes = settings.changed_from_defaults()
    if changes.get("api_key"):
        changes["api_key"] = "***"
    return changes


# --------------------------------------------------------------------------- #
def main() -> None:
    settings = sidebar()
    pipeline = get_pipeline(settings.index_key, settings)
    # The cached pipeline was built for this index, but not necessarily for the
    # current retrieval / generation controls — push those onto its stages.
    pipeline.apply(settings)
    sidebar_status(pipeline, settings)

    st.title("Dietary supplements for athletic performance — RAG explorer")
    ask, chunks, review, evaluate, index = st.tabs(
        ["Ask", "Chunks", "Review", "Evaluate", "Index"]
    )
    with ask:
        ask_tab(pipeline, settings)
    with chunks:
        chunks_tab(pipeline, settings)
    with review:
        review_tab()
    with evaluate:
        evaluate_tab(pipeline, settings)
    with index:
        index_tab(pipeline, settings)


main()
