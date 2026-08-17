"""Streamlit UI for the athletic-supplements RAG pipeline.

Run with:  streamlit run app.py

The point of the UI is the feedback loop: change chunk size / overlap / top-k,
see the chunks that produced, ask questions, and judge the retrieved chunks.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Dict, List

import streamlit as st

from rag.chunking import MarkdownChunker
from rag.config import Settings
from rag.diagnostics import ChunkInspector
from rag.fetching import SourceFetcher
from rag.pipeline import RAGPipeline
from rag.preprocessing import MarkdownCleaner
from rag.schema import Chunk, Retrieved

SEED_QUESTIONS = [
    "Does creatine improve athletic performance?",
    "How much beta-alanine is needed to improve exercise performance?",
    "Are there safety concerns with taking beetroot juice before exercise?",
    "Does caffeine help endurance athletes?",
]
VERDICTS = ["unjudged", "relevant", "not relevant"]

# Retry/failure messages from the pipeline. A plain deque rather than
# `st.session_state` because question generation logs from worker threads, and
# session state may only be touched from the main thread.
LOG: deque = deque(maxlen=200)

st.set_page_config(page_title="Athletic Supplements RAG", page_icon="🏃", layout="wide")


# --------------------------------------------------------------------------- #
# Cached pipeline pieces
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner="Fetching, cleaning and chunking…")
def load_chunks(
    source: str, url: str, cache_dir: str, chunk_size: int, overlap: int,
    min_chars: int, prepend_section: bool,
) -> List[Chunk]:
    """Chunking only — no embeddings, so this is free to re-run on every slider move."""
    stages = (
        SourceFetcher(url=url, cache_dir=cache_dir)
        | MarkdownCleaner()
        | MarkdownChunker(chunk_size, overlap, min_chars, prepend_section)
    )
    return stages(source)


@st.cache_resource(show_spinner=False)
def get_pipeline(
    source: str, chunk_size: int, overlap: int, min_chars: int,
    questions_per_chunk: int, prepend_section: bool, db_path: str,
) -> RAGPipeline:
    """One pipeline (and Chroma collection) per chunking configuration.

    Every argument here also appears in `Settings.collection_name`, so a cached
    pipeline can never be paired with an index built from other settings.
    """
    return RAGPipeline(
        Settings.from_env(
            source=source,
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            min_chunk_chars=min_chars,
            questions_per_chunk=questions_per_chunk,
            prepend_section=prepend_section,
            db_path=db_path,
        ),
        log=LOG.append,
    )


def state(key: str, default):
    return st.session_state.setdefault(key, default)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar() -> Settings:
    defaults = Settings.from_env()
    st.sidebar.title("🏃 Pipeline settings")

    source = st.sidebar.text_input("Source (HTML file or URL)", value=defaults.source)

    st.sidebar.subheader("Chunking")
    chunk_size = st.sidebar.slider("Chunk size (chars)", 200, 2000, defaults.chunk_size, 50)
    overlap = st.sidebar.slider("Overlap (chars)", 0, 500, defaults.chunk_overlap, 25)
    if overlap >= chunk_size:
        overlap = chunk_size // 4
        st.sidebar.warning(f"Overlap must stay below chunk size — using {overlap}.")
    min_chars = st.sidebar.slider("Merge fragments below (chars)", 0, 300, defaults.min_chunk_chars, 10)
    prepend_section = st.sidebar.checkbox(
        "Prefix chunks with their heading path", value=defaults.prepend_section,
        help="Turns '#### Efficacy' into 'Creatine > Efficacy' inside the chunk text.",
    )

    st.sidebar.subheader("Retrieval")
    top_k = st.sidebar.slider("Top-k results", 1, 20, defaults.top_k)
    dedupe = st.sidebar.checkbox(
        "One result per chunk", value=defaults.dedupe_by_chunk,
        help="Collapse a chunk and its hypothetical questions into a single result.",
    )

    st.sidebar.subheader("Indexing")
    questions_per_chunk = st.sidebar.slider(
        "Hypothetical questions per chunk", 0, 5, defaults.questions_per_chunk,
        help="Indexed alongside each chunk so user-style questions have something "
             "question-shaped to match. Costs one generation request per chunk, "
             "and free models have a daily cap. 0 disables it entirely.",
    )

    return defaults.with_(
        source=source,
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        min_chunk_chars=min_chars,
        prepend_section=prepend_section,
        top_k=top_k,
        dedupe_by_chunk=dedupe,
        questions_per_chunk=questions_per_chunk,
    )


def sidebar_status(pipeline: RAGPipeline, settings: Settings) -> None:
    st.sidebar.subheader("Index")
    st.sidebar.caption(f"Collection `{settings.collection_name}`")
    st.sidebar.metric("Rows indexed", f"{pipeline.index.count:,}")

    if pipeline.offline:
        st.sidebar.error(
            "No `OPENROUTER_API_KEY` — running on offline hash embeddings. "
            "Retrieval quality will be poor; set the key in `.env` for real results."
        )

    build, reset = st.sidebar.columns(2)
    if build.button("Build index", type="primary", use_container_width=True):
        run_build(pipeline, force=False)
    if reset.button("Rebuild", use_container_width=True,
                    help="Delete this collection and index again from scratch"):
        run_build(pipeline, force=True)


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
    pipeline.retriever.top_k = top_k
    pipeline.retriever.dedupe = pipeline.settings.dedupe_by_chunk
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
    if header[3].button("Generate answer", key=f"answer-{question}",
                        disabled=pipeline.offline, use_container_width=True):
        with st.spinner("Answering…"):
            state("answers", {})[question] = pipeline.answer(question, hits)

    if answer := state("answers", {}).get(question):
        st.success(answer)

    for position, hit in enumerate(hits, start=1):
        render_hit(question, position, hit)
    st.divider()


def render_hit(question: str, position: int, hit: Retrieved) -> None:
    badge = "❓ question match" if hit.match_type == "question" else "📄 chunk match"
    title = (
        f"**{position}. {hit.section or 'document'}** — similarity "
        f"{hit.similarity:.3f} · {badge} · {len(hit.text)} chars"
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
            "similarity": round(hit.similarity, 4),
            "match_type": hit.match_type,
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
        chunks = load_chunks(
            settings.source, settings.source_url, str(settings.cache_dir),
            settings.chunk_size, settings.chunk_overlap,
            settings.min_chunk_chars, settings.prepend_section,
        )
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not read the source: {exc}")
        return

    report = ChunkInspector(chunk_size=settings.chunk_size)(chunks)
    columns = st.columns(5)
    columns[0].metric("Chunks", report.total)
    columns[1].metric("Sections", report.sections)
    columns[2].metric("Median chars", f"{report.median_chars:.0f}")
    columns[3].metric("Max chars", report.max_chars)
    columns[4].metric("Flagged", len(report.flags))
    requests = pipeline.requests_for_build(report.total)
    st.caption(
        f"Rows this configuration would index: {report.total} chunks + up to "
        f"{report.total * settings.questions_per_chunk} questions = "
        f"**{report.total * (1 + settings.questions_per_chunk)}** embeddings — "
        f"about **{requests} API requests**, roughly "
        f"**{requests / max(settings.requests_per_minute, 1):.0f} min** at "
        f"{settings.requests_per_minute} requests/minute."
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
            f"section: {c.section or '-'}\n{'=' * 70}\n{c.text}\n"
            for c in chunks
        ),
        file_name=f"chunks_c{settings.chunk_size}_o{settings.chunk_overlap}.md",
    )

    for chunk in shown[:200]:
        flags = " ".join(report.flags.get(chunk.index, [])) or "ok"
        with st.expander(f"**[{chunk.index}]** {chunk.section or 'document'} — "
                         f"{chunk.size} chars · {flags}"):
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
            f"`{settings.llm_model}` · paced at {settings.requests_per_minute} "
            "requests/minute"
        )

    if pipeline.index.count:
        st.write("Row types:", pipeline.index.stats())

    st.subheader("Collections on disk")
    st.write(pipeline.index.collections() or "none yet")
    st.caption(
        "Each chunking configuration gets its own collection, so switching the "
        "sliders back to a previous setting reuses the index you already built."
    )

    if LOG:
        st.subheader("Pipeline log")
        st.code("\n".join(LOG))


# --------------------------------------------------------------------------- #
def main() -> None:
    settings = sidebar()
    pipeline = get_pipeline(
        settings.source, settings.chunk_size, settings.chunk_overlap,
        settings.min_chunk_chars, settings.questions_per_chunk,
        settings.prepend_section, str(settings.db_path),
    )
    # The cached pipeline predates the current retrieval sliders — keep it in sync.
    pipeline.settings = pipeline.settings.with_(
        top_k=settings.top_k, dedupe_by_chunk=settings.dedupe_by_chunk,
    )
    sidebar_status(pipeline, settings)

    st.title("Dietary supplements for athletic performance — RAG explorer")
    ask, chunks, review, index = st.tabs(["Ask", "Chunks", "Review", "Index"])
    with ask:
        ask_tab(pipeline, settings)
    with chunks:
        chunks_tab(pipeline, settings)
    with review:
        review_tab()
    with index:
        index_tab(pipeline, settings)


main()
