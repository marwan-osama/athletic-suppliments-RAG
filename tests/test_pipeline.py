"""Offline tests — no API key, no network.

    python tests/test_pipeline.py     (or: pytest tests)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx

import ast
from dataclasses import fields

from rag.augmentation import QuestionGenerator, parse_questions
from rag.chunking import MarkdownChunker
from rag.config import DOCUMENT_PREFIX, QUERY_PREFIX, Settings, env_flag
from rag.diagnostics import LINK_HEAVY, OVERSIZED, TINY, ChunkInspector
from rag.embedding import HashEmbedder, ServerEmbedder, _normalize
from rag.expansion import QueryExpander
from rag.indexing import VectorIndex
from rag.llm import LLMClient, LLMError, RateLimiter
from rag.pipeline import DISABLED_NOTICE, RAGPipeline, reader
from rag.preprocessing import MarkdownCleaner
from rag.retrieval import Retriever
from rag.schema import Chunk, Identity, Stage

MESSY = """# Dietary Supplements for Exercise and Athletic Performance

Have a question? [Ask ODS](https://ods.od.nih.gov/contact)

Join the [ODS Email List](https://ods.od.nih.gov/News/ODS_ListServ.aspx)

-

## Creatine

### <sub>10</sub>)

#### Efficacy

Creatine is one of the most thoroughly studied supplements [[112](https://ods.od.nih.gov#en112)].
It helps generate ATP and thereby supplies the muscles with energy for short bursts
of activity, such as sprinting and weightlifting [[112](https://ods.od.nih.gov#en112),[113](https://ods.od.nih.gov#en113)].

#### Safety

Creatine is considered safe for healthy adults at recommended doses.

## References

1. Some reference nobody should retrieve.
2. Another reference entry.
"""


def test_cleaner_strips_links_citations_and_nav():
    clean = MarkdownCleaner()(MESSY)

    assert "https://" not in clean, "no URLs should survive"
    assert "Ask ODS" not in clean and "ODS Email List" not in clean
    assert "[112]" not in clean, "citation markers should be dropped"
    assert "<sub>" not in clean
    assert "nobody should retrieve" not in clean, "References section is dropped"
    assert "generate ATP" in clean, "prose must survive"


def test_cleaner_names_empty_headings_from_their_first_sentence():
    """Every supplement heading on the real page extracts as a bare `### `."""
    raw = (
        "### \n\nHMB is a metabolite of the amino acid leucine.\n\n"
        "#### Efficacy\n\nStudies have investigated HMB for two decades.\n\n"
        "### \n\nBetaine, also known as trimethylglycine, is found in beets.\n\n"
        "### \n\n#### Efficacy\n\nNothing names the heading above.\n"
    )
    clean = MarkdownCleaner()(raw)

    assert "### HMB" in clean
    assert "### Betaine" in clean, clean
    # A heading followed straight by another heading has nothing to borrow.
    level_three = [
        line for line in clean.splitlines()
        if line.startswith("### ") and not line.startswith("#### ")
    ]
    assert level_three == ["### HMB", "### Betaine"], level_three

    sections = {c.section for c in MarkdownChunker(300, 40, 40)(clean)}
    assert "HMB > Efficacy" in sections, sections


def test_chunker_attaches_headings_and_respects_size():
    chunks = MarkdownChunker(chunk_size=300, chunk_overlap=50, min_chars=60)(
        MarkdownCleaner()(MESSY)
    )

    assert chunks, "expected chunks"
    assert all(chunk.size <= 300 for chunk in chunks), "no chunk may exceed chunk_size"
    assert any("Creatine > Efficacy" in chunk.text for chunk in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks))), "indices are dense"

    # A heading with no prose under it must never become a chunk of its own:
    # every chunk body (the text after the heading path) carries real content.
    bodies = [chunk.text.split("\n\n", 1)[-1].strip() for chunk in chunks]
    assert all(len(body) >= 20 for body in bodies), bodies


def test_chunk_ids_are_stable_and_content_derived():
    first = MarkdownChunker(400, 40)(MarkdownCleaner()(MESSY))
    second = MarkdownChunker(400, 40)(MarkdownCleaner()(MESSY))

    assert [c.id for c in first] == [c.id for c in second], "ids must be reproducible"
    assert len({c.id for c in first}) == len(first), "ids must be unique"


def test_stage_composition_operator():
    chain = MarkdownCleaner() | MarkdownChunker(500, 50)
    assert isinstance(chain, Stage)
    assert len(chain.stages) == 2
    assert chain(MESSY) == MarkdownChunker(500, 50)(MarkdownCleaner()(MESSY))


def test_inspector_flags():
    inspector = ChunkInspector(chunk_size=100, tiny_below=20)
    assert OVERSIZED in inspector.flags_for("x" * 200)
    assert TINY in inspector.flags_for("short")
    assert LINK_HEAVY in inspector.flags_for("[a](1) [b](2) [c](3) [d](4) [e](5)")

    report = inspector([Chunk(0, "x" * 200), Chunk(1, "fine enough text here")])
    assert report.total == 2
    assert report.count(OVERSIZED) == 1


def test_parse_questions_strips_bullets_and_numbers():
    raw = "1. What is creatine?\n- Is it safe?\n\n* How much per day?\n"
    assert parse_questions(raw) == [
        "What is creatine?",
        "Is it safe?",
        "How much per day?",
    ]
    assert parse_questions(raw, limit=2) == ["What is creatine?", "Is it safe?"]


def test_normalize_returns_unit_vectors():
    vector = _normalize([3.0, 4.0])
    assert abs(sum(v * v for v in vector) - 1.0) < 1e-9
    assert _normalize([0.0, 0.0]) == [0.0, 0.0], "zero vector must not divide by zero"


def test_index_and_retrieve_end_to_end():
    """Index real chunks with the offline embedder and search them."""
    chunks = MarkdownChunker(chunk_size=300, chunk_overlap=50)(MarkdownCleaner()(MESSY))
    questions = {chunks[0].id: ["What does creatine do for sprinting?"]}

    with tempfile.TemporaryDirectory() as tmp:
        index = VectorIndex(HashEmbedder(), db_path=tmp, collection_name="test")
        rows = index.add(chunks, questions)
        assert rows == len(chunks) + 1
        assert index.count == rows
        assert index.stats()["question"] == 1

        # Re-adding the same chunks must not create duplicates (content-derived ids).
        assert index.add(chunks, questions) == rows
        assert index.count == rows

        results = Retriever(index, top_k=2)("creatine energy sprinting muscles")
        assert results, "expected at least one result"
        assert len(results) <= 2
        assert all(result.text for result in results), "parent text must be resolved"
        assert len({result.chunk_id for result in results}) == len(results)
        assert results == sorted(results, key=lambda r: -r.similarity)

        index.reset()
        assert index.count == 0


# --------------------------------------------------------------------------- #
# The model server: request/response contract, against a mock transport
# --------------------------------------------------------------------------- #
def fake_client(handler, **kwargs) -> LLMClient:
    """A client whose requests are served by `handler` instead of the network."""
    return LLMClient(
        api_key="test-key",
        requests_per_minute=0,  # no pacing in tests
        transport=httpx.MockTransport(handler),
        log=lambda message: None,
        **kwargs,
    )


def embedding_response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    # Answer out of order on purpose: `index` is what the client must trust.
    rows = [
        {"embedding": [float(position + 1), 0.0], "index": position}
        for position, _ in enumerate(body["input"])
    ]
    return httpx.Response(200, json={"data": list(reversed(rows))})


def test_auth_header_only_when_a_key_is_given():
    """LM Studio needs no credentials; hosted gateways do."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"data": []})

    LLMClient(transport=httpx.MockTransport(handler)).models()
    assert seen["auth"] is None, "no key means no Authorization header"

    LLMClient(api_key="k", transport=httpx.MockTransport(handler)).models()
    assert seen["auth"] == "Bearer k"


def test_unreachable_server_says_so_plainly():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    try:
        LLMClient(transport=httpx.MockTransport(handler),
                  log=lambda message: None).complete("m", "hi")
    except LLMError as error:
        assert "Cannot reach the model server" in str(error), error
        assert "LM Studio" in str(error)
    else:
        raise AssertionError("a refused connection must raise")


def test_embed_sends_openai_shape_and_orders_by_index():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return embedding_response(request)

    client = fake_client(handler)
    vectors = client.embed("text-embedding-embeddinggemma-300m", ["a", "b", "c"])

    assert seen["url"] == "http://127.0.0.1:1234/v1/embeddings"
    assert seen["auth"] == "Bearer test-key"
    assert seen["body"]["model"] == "text-embedding-embeddinggemma-300m"
    assert seen["body"]["input"] == ["a", "b", "c"]
    assert seen["body"]["encoding_format"] == "float"
    # Reversed by the server, restored by the client.
    assert vectors == [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]]


def test_embedder_applies_asymmetric_prefixes_and_normalizes():
    inputs = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs.append(json.loads(request.content)["input"])
        return embedding_response(request)

    embedder = ServerEmbedder(
        fake_client(handler), model_name="embed", batch_size=2,
        document_prefix=DOCUMENT_PREFIX, query_prefix=QUERY_PREFIX,
    )

    document_vectors = embedder(["chunk one", "chunk two", "chunk three"])
    embedder.embed_query("does creatine work?")

    assert inputs[0] == [f"{DOCUMENT_PREFIX}chunk one", f"{DOCUMENT_PREFIX}chunk two"], inputs[0]
    assert inputs[1] == [f"{DOCUMENT_PREFIX}chunk three"], "batch_size must be respected"
    assert inputs[2] == [f"{QUERY_PREFIX}does creatine work?"], inputs[2]
    assert all(
        abs(sum(value * value for value in vector) - 1.0) < 1e-9
        for vector in document_vectors
    ), "vectors must come back normalized"
    assert embedder.dimensions == 768


def test_retries_on_429_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="slow down")
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    assert fake_client(handler).complete("m", "hi") == "ok"
    assert len(attempts) == 2, "the 429 should have been retried once"


def test_client_does_not_retry_a_bad_request():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(400, text='{"error":"unknown model"}')

    try:
        fake_client(handler).complete("nope", "hi")
    except LLMError as error:
        assert error.status == 400
        assert "unknown model" in str(error)
    else:
        raise AssertionError("a 400 must raise")
    assert len(calls) == 1, "a 400 must not be retried"


def test_complete_sends_no_reasoning_field_and_strips_think_blocks():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "<think>hmm</think>What is HMB?"}}
                ]
            },
        )

    generator = QuestionGenerator(fake_client(handler), num_questions=2)
    questions = generator.for_text("HMB is a metabolite of leucine.")

    assert "reasoning" not in seen, "both models ignore it, so it is not sent"
    assert seen["messages"][0]["role"] == "user"
    assert questions == ["What is HMB?"], questions


def test_empty_reply_from_a_spent_token_budget_is_reported():
    """Reasoning is charged against max_tokens; running out yields content=None."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": None}, "finish_reason": "length"}],
                "usage": {"completion_tokens_details": {"reasoning_tokens": 39}},
            },
        )

    try:
        fake_client(handler).complete("m", "hi", max_tokens=32)
    except LLMError as error:
        assert "max_tokens" in str(error), error
        assert "reasoning_tokens=39" in str(error), error
    else:
        raise AssertionError("an empty reply must not pass as a valid answer")


def test_generation_failure_skips_the_chunk_without_failing_the_build():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error":"nope"}')

    generator = QuestionGenerator(
        fake_client(handler), num_questions=2, log=lambda message: None
    )
    assert generator.run([Chunk(0, "some text")]) == {}


def test_rate_limiter_spacing():
    assert RateLimiter(20).interval == 3.0, "20/minute is one request every 3s"
    assert RateLimiter(0).interval == 0.0, "0 disables pacing"


def test_enable_questions_switch_wins_over_the_count():
    on = Settings(api_key="k", questions_per_chunk=3)
    off = Settings(api_key="k", questions_per_chunk=3, enable_questions=False)

    assert on.questions_per_chunk == 3
    assert off.questions_per_chunk == 0, "the switch must override the count"
    assert "_q3_" in on.collection_name
    assert "_q0_" in off.collection_name, "disabled questions get their own index"
    # Copies made by the CLI/UI override path cannot switch it back on.
    assert off.with_(questions_per_chunk=5).questions_per_chunk == 0


def test_enable_questions_reads_the_environment():
    for value, expected in [
        ("true", 3), ("TRUE", 3), ("1", 3), ("yes", 3), ("on", 3),
        ("false", 0), ("0", 0), ("no", 0), ("off", 0),
    ]:
        os.environ["RAG_ENABLE_QUESTIONS"] = value
        try:
            actual = Settings.from_env(questions_per_chunk=3).questions_per_chunk
        finally:
            os.environ.pop("RAG_ENABLE_QUESTIONS")
        assert actual == expected, f"RAG_ENABLE_QUESTIONS={value!r} gave {actual}"

    assert env_flag("RAG_ENABLE_QUESTIONS", default=True) is True, "unset = default"


def test_settings_default_to_the_local_server():
    settings = Settings(api_key="k")
    assert settings.embed_model == "text-embedding-embeddinggemma-300m"
    assert settings.llm_model == "openai/gpt-oss-20b"
    assert settings.embedder_tag == "embeddinggem", settings.embedder_tag
    assert Settings(offline=True).embedder_tag == "hash"
    # Chroma rejects collection names longer than 63 characters.
    assert len(settings.collection_name) <= 63, settings.collection_name


# --------------------------------------------------------------------------- #
# Query expansion
# --------------------------------------------------------------------------- #
def expanding_client(reply: str) -> LLMClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": reply}}]})

    return fake_client(handler)


def test_expander_keeps_the_original_query_first():
    expander = QueryExpander(
        expanding_client("1. creatine sprint performance\n- phosphocreatine ATP"),
        num_expansions=2,
    )
    assert expander("does creatine help sprinting?") == [
        "does creatine help sprinting?",
        "creatine sprint performance",
        "phosphocreatine ATP",
    ]


def test_expander_degrades_to_the_plain_query():
    """A search that cannot be expanded is still a search."""

    def failing(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error":"nope"}')

    logged = []
    expander = QueryExpander(
        fake_client(failing), num_expansions=2, log=logged.append
    )
    assert expander("is HMB safe?") == ["is HMB safe?"]
    assert logged and "query expansion" in logged[0], logged

    # ...and the count is the switch, so zero never reaches the server.
    never = QueryExpander(expanding_client("unused"), num_expansions=0)
    assert never("is HMB safe?") == ["is HMB safe?"]
    assert QueryExpander(expanding_client("x"), num_expansions=2)("  ") == ["  "]


def test_expander_drops_a_phrasing_identical_to_the_query():
    expander = QueryExpander(
        expanding_client("is HMB safe?\nHMB side effects"), num_expansions=2
    )
    assert expander("is HMB safe?") == ["is HMB safe?", "HMB side effects"]


def test_agreement_boosts_the_rank_but_never_the_similarity():
    """The number on screen stays the one the embedder returned."""
    chunks = MarkdownChunker(chunk_size=300, chunk_overlap=50)(MarkdownCleaner()(MESSY))

    with tempfile.TemporaryDirectory() as tmp:
        index = VectorIndex(HashEmbedder(), db_path=tmp, collection_name="test")
        index.add(chunks)

        # Two phrasings, both of which find the creatine passage.
        expander = QueryExpander(
            expanding_client("creatine ATP muscles energy"), num_expansions=1
        )
        retriever = Retriever(index, top_k=3, expander=expander, match_boost=0.05)
        agreed = retriever("creatine energy sprinting muscles")

        assert agreed, "expected results"
        best = agreed[0]
        assert best.matches == 2, "both phrasings found it"
        assert best.boost == 0.05
        assert best.score == best.similarity + 0.05
        assert best.similarity < 1.0 and best.score > best.similarity

        # Without expansion nothing is boosted, however many rows matched.
        plain = Retriever(index, top_k=3)("creatine energy sprinting muscles")
        assert all(hit.matches == 1 and hit.boost == 0.0 for hit in plain)
        assert all(hit.score == hit.similarity for hit in plain)


def test_a_chunks_own_questions_are_not_mistaken_for_agreement():
    """One vote per phrasing — not per matching row.

    A chunk indexed with three hypothetical questions can match through all of
    them on a single query. That is one phrasing agreeing with itself, and must
    not read as four independent confirmations.
    """
    chunk = Chunk(0, "Creatine helps generate ATP for short bursts of activity.")
    questions = {chunk.id: ["What does creatine do?", "Is creatine for sprinting?"]}

    with tempfile.TemporaryDirectory() as tmp:
        index = VectorIndex(HashEmbedder(), db_path=tmp, collection_name="test")
        index.add([chunk], questions)

        results = Retriever(index, top_k=3)("creatine ATP sprinting")
        assert results, "expected a result"
        assert all(hit.matches == 1 for hit in results), [h.matches for h in results]
        assert all(hit.boost == 0.0 for hit in results)


def test_expansion_does_not_duplicate_results_without_dedupe():
    """`dedupe=False` keeps questions separate from chunks, not repeats of a row."""
    chunk = Chunk(0, "Beta-alanine buffers acid and delays muscular fatigue.")
    questions = {chunk.id: ["How does beta-alanine work?"]}

    with tempfile.TemporaryDirectory() as tmp:
        index = VectorIndex(HashEmbedder(), db_path=tmp, collection_name="test")
        index.add([chunk], questions)

        expander = QueryExpander(
            expanding_client("beta alanine fatigue buffering"), num_expansions=1
        )
        results = Retriever(index, top_k=5, dedupe=False, expander=expander)(
            "beta-alanine muscular fatigue"
        )
        seen = [(hit.chunk_id, hit.matched_text) for hit in results]
        assert len(seen) == len(set(seen)), f"a row came back twice: {seen}"


def test_query_expansion_is_query_time_and_never_touches_the_index():
    """Expansion changes what is searched for, not what is stored."""
    settings = Settings()
    assert settings.collection_name == settings.with_(query_expansions=7).collection_name
    assert settings.index_key == settings.with_(query_expansions=7).index_key
    assert settings.reader_key == settings.with_(match_boost=0.2).reader_key
    # The switch collapses into the count, like the questions switch does.
    off = Settings(enable_query_expansion=False, query_expansions=4)
    assert off.query_expansions == 0
    assert off.with_(query_expansions=9).query_expansions == 0


# --------------------------------------------------------------------------- #
# Optional stages: every one of them can be switched off
# --------------------------------------------------------------------------- #
def test_cleaning_can_be_bypassed():
    """`enable_cleaning=False` chunks the raw extraction, link soup and all."""
    on = reader(Settings(enable_cleaning=True))
    off = reader(Settings(enable_cleaning=False))

    assert isinstance(off.stages[1], Identity), "the cleaner must drop out entirely"
    assert not isinstance(on.stages[1], Identity)

    # Straight through the two stages that remain, skipping the fetch.
    raw = (off.stages[1] | off.stages[2])(MESSY)
    cleaned = (on.stages[1] | on.stages[2])(MESSY)
    assert any("https://" in chunk.text for chunk in raw), "nothing was cleaned"
    assert all("https://" not in chunk.text for chunk in cleaned)
    assert any("nobody should retrieve" in c.text for c in raw), "References survive"


def test_every_stage_setting_reaches_its_stage():
    """The knobs are wired to the objects, not just stored on `Settings`."""
    settings = Settings(
        offline=True, chunk_size=400, chunk_overlap=20, min_chunk_chars=15,
        max_section_chars=30, fetch_min_chars=7, use_cache=False, tiny_below=33,
        top_k=9, dedupe_by_chunk=False, retrieval_overfetch=4,
        drop_sections=("references",), strip_citations=False,
    )
    fetcher, cleaner, chunker = reader(settings).stages

    assert (fetcher.use_cache, fetcher.min_chars) == (False, 7)
    assert (cleaner.drop_sections, cleaner.strip_citations) == (("references",), False)
    assert (chunker.chunk_size, chunker.chunk_overlap) == (400, 20)
    assert (chunker.min_chars, chunker.max_section_chars) == (15, 30)

    with tempfile.TemporaryDirectory() as tmp:
        pipeline = RAGPipeline(settings.with_(db_path=tmp), log=lambda message: None)
        assert pipeline.inspector.tiny_below == 33
        assert (pipeline.retriever.top_k, pipeline.retriever.dedupe) == (9, False)
        assert pipeline.retriever.overfetch == 4

        # ...and `apply` moves them again without rebuilding anything.
        index = pipeline.index
        pipeline.apply(pipeline.settings.with_(top_k=2, dedupe_by_chunk=True,
                                               retrieval_overfetch=6, tiny_below=5))
        assert (pipeline.retriever.top_k, pipeline.retriever.overfetch) == (2, 6)
        assert pipeline.retriever.dedupe is True
        assert pipeline.inspector.tiny_below == 5
        assert pipeline.index is index, "a runtime change must not reopen the index"


def test_expansion_switch_is_separate_from_being_offline():
    with tempfile.TemporaryDirectory() as tmp:
        off = RAGPipeline(
            Settings(db_path=tmp, enable_query_expansion=False),
            log=lambda message: None,
        )
        assert off.expander is not None, "the stage exists; its count is zero"
        assert off.can_expand is False
        assert off.retriever.expander("anything") == ["anything"]

        offline = RAGPipeline(
            Settings(db_path=tmp, offline=True), log=lambda message: None
        )
        assert offline.expander is None and offline.can_expand is False

        # ...and `apply` turns it back on without rebuilding the index.
        on = RAGPipeline(Settings(db_path=tmp), log=lambda message: None)
        index = on.index
        on.apply(on.settings.with_(query_expansions=5, query_expansion_temperature=1.1))
        assert on.expander.num_expansions == 5
        assert on.expander.temperature == 1.1
        assert on.index is index, "a query-time change must not reopen the index"


def test_answering_switch_is_separate_from_being_offline():
    with tempfile.TemporaryDirectory() as tmp:
        off = RAGPipeline(
            Settings(db_path=tmp, enable_answers=False), log=lambda message: None
        )
        assert off.answerer is not None, "the stage exists; it is just not used"
        assert off.can_answer is False
        assert off.answer("q", []) == DISABLED_NOTICE

        offline = RAGPipeline(
            Settings(db_path=tmp, offline=True), log=lambda message: None
        )
        assert offline.answerer is None and offline.can_answer is False


def test_bypassing_a_stage_gets_its_own_collection():
    """Two configurations that index different text may never share vectors."""
    default = Settings()
    names = {
        default.collection_name,
        default.with_(enable_cleaning=False).collection_name,
        default.with_(strip_links=False).collection_name,
        default.with_(document_prefix="").collection_name,
        default.with_(max_section_chars=40).collection_name,
    }
    assert len(names) == 5, "each variant needs an index of its own"
    assert all(len(name) <= 63 for name in names), names
    # The all-defaults name keeps the shape it had before these knobs existed,
    # so indexes already on disk stay reachable.
    assert default.index_variant == ""
    assert default.collection_name.endswith("_q3_m80_s1")


def test_extra_body_is_merged_into_chat_requests_without_overriding_the_caller():
    """Gateway routing rides along with every request, but never wins a clash.

    OpenRouter serves one model id from providers at different quantizations,
    and which one answers changes how much the model reasons — enough to empty
    a reply that fits at one provider and truncates at another.
    """
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "ok"}}]}
        )

    routing = {"provider": {"quantizations": ["fp4"], "allow_fallbacks": False}}
    client = LLMClient(
        transport=httpx.MockTransport(handler), extra_body=routing,
        log=lambda *_: None,
    )
    client.complete(model="m", prompt="hi", reasoning_effort="low")
    assert seen["provider"] == routing["provider"]
    # The per-call value survives; the merge only fills what is missing.
    assert seen["reasoning"] == {"effort": "low"}

    # And it is off unless asked for.
    plain = LLMClient(transport=httpx.MockTransport(handler), log=lambda *_: None)
    seen.clear()
    plain.complete(model="m", prompt="hi")
    assert "provider" not in seen


def test_extra_body_is_json_and_says_so_when_it_is_not():
    assert Settings().extra_body() == {}
    good = Settings(llm_extra_body='{"provider": {"quantizations": ["fp4"]}}')
    assert good.extra_body()["provider"]["quantizations"] == ["fp4"]
    for broken in ('{"provider":', '"a string"', "[1, 2]"):
        try:
            Settings(llm_extra_body=broken).extra_body()
        except ValueError:
            continue
        raise AssertionError(f"accepted invalid extra body: {broken}")


def test_embeddings_can_be_served_from_a_different_host_than_generation():
    """Generation on a gateway, embeddings on the machine that has the model.

    The index's vectors came from one embedding model, so moving generation to
    a hosted endpoint must leave the embedder where it is — and OpenRouter,
    the case this exists for, serves no /embeddings to move it to.
    """
    settings = Settings()
    assert settings.embed_endpoint() == (settings.base_url, settings.api_key)

    split = settings.with_(
        base_url="https://openrouter.ai/api/v1", api_key="generation-key",
        embed_base_url="http://127.0.0.1:1234/v1",
    )
    # Blank `embed_api_key` inherits, because the usual local server wants none.
    assert split.embed_endpoint() == ("http://127.0.0.1:1234/v1", "generation-key")
    assert split.with_(embed_api_key="own").embed_endpoint()[1] == "own"

    # Same vectors, same model: the collection must not fork over a hostname,
    # or pointing at a second host would orphan an index already on disk.
    assert split.collection_name == settings.collection_name
    assert split.index_variant == settings.index_variant
    # It does reach a different server, though, so it is a different pipeline.
    assert split.index_key != settings.index_key


def test_a_split_embedding_endpoint_gets_its_own_client():
    settings = Settings(embed_base_url="http://embeddings.local/v1")
    pipeline = RAGPipeline(settings, log=lambda *_: None)
    assert pipeline.embed_client is not pipeline.client
    assert pipeline.embed_client.base_url.startswith("http://embeddings.local")
    assert pipeline.embedder.client is pipeline.embed_client

    # Unsplit, there is one client and therefore one shared rate limiter.
    shared = RAGPipeline(Settings(), log=lambda *_: None)
    assert shared.embed_client is shared.client


def test_settings_round_trip_through_json():
    settings = Settings(
        chunk_size=750, enable_cleaning=False, drop_sections="references, notes",
        reasoning_effort="high", api_key="secret", db_path="/tmp/x",
    )
    assert Settings.from_json(settings.to_json()) == settings
    assert settings.redacted()["api_key"] == "***"
    assert "***" not in settings.to_json(), "redaction is for display only"
    assert settings.reader_key == settings.with_(top_k=19).reader_key
    assert settings.index_key != settings.with_(chunk_size=751).index_key


def test_the_ui_exposes_every_setting():
    """Each `*_controls` function in app.py returns Settings fields by name.

    Their union has to be every field, or a hyperparameter exists that the
    sidebar cannot reach — which is the one thing this UI promises.
    """
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    exposed = {
        key.value
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef) and function.name.endswith("_controls")
        for node in ast.walk(function)
        if isinstance(node, ast.Dict)
        for key in node.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    missing = {field.name for field in fields(Settings)} - exposed
    assert not missing, f"no sidebar control for: {sorted(missing)}"


# --------------------------------------------------------------------------- #
# PDF reading and page provenance
# --------------------------------------------------------------------------- #
PAGED = """<!--page:3-->
# Creatine

Creatine helps generate ATP and thereby supplies the muscles with energy for
short-term events, which is why it suits sprinting rather than distance running.

<!--page:4-->
It is of little value for endurance sports, and the weight gain it causes might
impede performance in them.

## Safety

<!--page:5-->
Creatine is considered safe for short-term use by healthy adults.
"""


def test_page_markers_survive_cleaning():
    """The chunker can only attribute pages if the cleaner leaves markers alone."""
    from rag.fetching import read_pages

    cleaned = MarkdownCleaner()(PAGED)
    assert read_pages(cleaned) == (3, 4, 5), read_pages(cleaned)


def test_chunks_carry_their_page_and_never_keep_the_marker():
    from rag.fetching import read_pages

    chunks = MarkdownChunker(chunk_size=300, chunk_overlap=0, min_chars=20)(
        MarkdownCleaner()(PAGED)
    )
    assert chunks, "expected chunks"
    assert all(chunk.pages for chunk in chunks), "every chunk must know its page"
    # The marker is provenance, not content: it must not reach the index.
    assert not any(read_pages(chunk.text) for chunk in chunks)
    assert min(min(c.pages) for c in chunks) == 3
    assert max(max(c.pages) for c in chunks) == 5


def test_text_continuing_past_a_page_break_cites_both_pages():
    """A chunk that straddles a break belongs to both pages, not just the later one."""
    chunks = MarkdownChunker(chunk_size=4_000, chunk_overlap=0, min_chars=20)(
        MarkdownCleaner()(PAGED)
    )
    spanning = [chunk for chunk in chunks if len(chunk.pages) > 1]
    assert spanning, "one chunk should cover the run-on paragraph across pages 3-4"
    assert spanning[0].pages[:2] == (3, 4), spanning[0].pages


def test_page_label_reads_as_a_citation():
    from rag.schema import page_label

    assert page_label(()) == ""
    assert page_label((7,)) == "p. 7"
    assert page_label((7, 8, 9)) == "pp. 7-9"
    # A gap is never smoothed into a range that includes a page not in the chunk.
    assert page_label((7, 9)) == "pp. 7, 9"


def test_pages_round_trip_through_chroma_metadata():
    """Chroma stores scalars, so the tuple has to survive being flattened."""
    from rag.indexing import pages_from_metadata, pages_to_metadata

    assert pages_to_metadata((7, 8)) == "7,8"
    assert pages_from_metadata("7,8") == (7, 8)
    assert pages_from_metadata("") == ()
    assert pages_from_metadata(None) == (), "rows indexed before pages existed"


def test_a_source_that_is_not_a_pdf_is_refused_before_the_cache():
    """A cache entry left by another source must not be served as PDF output."""
    from rag.fetching import PdfReader

    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "cache"
        cache.mkdir()
        # A cache file whose name matches what the HTML source would have written.
        (cache / "page.md").write_text("stale markdown, no page markers", encoding="utf-8")
        try:
            PdfReader(cache_dir=cache)("page.html")
        except ValueError as error:
            assert "not a PDF" in str(error), error
        else:
            raise AssertionError("a non-PDF source must be refused, cached or not")


def test_the_answerer_shows_each_source_page_to_the_model():
    """The page in a citation comes off the index, not out of the model."""
    from rag.answering import Answerer
    from rag.schema import Retrieved

    hit = Retrieved(
        chunk_id="c1", text="Creatine suits sprinting.", similarity=0.9,
        match_type="chunk", section="Creatine > Efficacy", pages=(12, 13),
    )
    formatted = Answerer(client=None)._format([hit])
    assert "(Creatine > Efficacy, pp. 12-13)" in formatted, formatted
    assert "p. " in Answerer.PROMPT, "the prompt must ask for the page"


def test_citations_get_the_page_from_the_index_not_from_the_model():
    """A small model writes a bare [3], or a page it liked. Neither is trusted."""
    from rag.answering import cite_pages
    from rag.schema import Retrieved

    def hit(pages):
        return Retrieved(
            chunk_id="c", text="", similarity=0.5, match_type="chunk", pages=pages
        )

    chunks = [hit((19,)), hit((4,)), hit((20, 21))]
    assert cite_pages("Loading [1]. Table [2]. Safety [3].", chunks) == (
        "Loading [1, p. 19]. Table [2, p. 4]. Safety [3, pp. 20-21]."
    )
    # A page the model invented is replaced by the real one.
    assert cite_pages("Claim [1, p. 99].", chunks) == "Claim [1, p. 19]."
    # A source that does not exist is left alone rather than quietly renumbered.
    assert cite_pages("Claim [7].", chunks) == "Claim [7]."
    # Models reach for fullwidth brackets — gpt-oss-20b used them in half the
    # answers of one evaluation run. Missing those would let an unverified page
    # through looking exactly like a checked one.
    assert cite_pages("Claim \u30104, p.\u202f9\u3011.", chunks + [hit((7,))]) == (
        "Claim [4, p. 7]."
    )
    assert cite_pages("Claim \u30102\u3011.", chunks) == "Claim [2, p. 4]."
    # A chunk with no page recorded must not grow an empty label.
    assert cite_pages("Claim [1].", [hit(())]) == "Claim [1]."


def test_a_different_pdf_gets_its_own_collection():
    """Two documents must never share one index."""
    assert (
        Settings(source="a.pdf").collection_name
        != Settings(source="b.pdf").collection_name
    )


# --------------------------------------------------------------------------- #
# Reranking
# --------------------------------------------------------------------------- #
def _hits(n):
    from rag.schema import Retrieved
    return [
        Retrieved(chunk_id=f"c{i}", text=f"passage {i}", similarity=0.9 - i / 100,
                  match_type="chunk", section=f"s{i}")
        for i in range(n)
    ]


class ScriptedClient:
    """An LLMClient stand-in that returns whatever the test scripted."""

    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0

    def complete(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.reply


def test_reranker_reorders_to_the_models_ranking():
    from rag.reranking import Reranker

    client = ScriptedClient(reply="3, 1, 2")
    ranked = Reranker(client, log=lambda _: None)("q", _hits(3))
    assert [h.chunk_id for h in ranked] == ["c2", "c0", "c1"], ranked
    assert client.calls == 1, "listwise: one call for the whole candidate list"
    # The dense position is kept so the UI can show what moved.
    assert [h.dense_rank for h in ranked] == [3, 1, 2]


def test_reranker_never_drops_a_candidate():
    """It reorders; truncation to top_k is the retriever's job, not the model's."""
    from rag.reranking import Reranker

    ranked = Reranker(ScriptedClient(reply="4"), log=lambda _: None)("q", _hits(5))
    assert len(ranked) == 5, "a chunk the model ignored must still be returned"
    assert ranked[0].chunk_id == "c3", "the chosen one leads"
    # The rest keep their dense order behind it.
    assert [h.chunk_id for h in ranked[1:]] == ["c0", "c1", "c2", "c4"]


def test_a_useless_ranking_degrades_to_dense_order():
    from rag.reranking import Reranker

    original = [h.chunk_id for h in _hits(4)]
    for reply in ("no idea", "", "99, 0", "passage seven please"):
        ranked = Reranker(ScriptedClient(reply=reply), log=lambda _: None)("q", _hits(4))
        assert [h.chunk_id for h in ranked] == original, reply

    # A reply that is only partly usable is used only partly: the one number in
    # range is promoted, the rest keep their dense order. Nothing is discarded
    # because the model wrote something odd around it.
    ranked = Reranker(ScriptedClient(reply="99, 0, 3"), log=lambda _: None)("q", _hits(4))
    assert [h.chunk_id for h in ranked] == ["c2", "c0", "c1", "c3"], ranked
    # A server that is down costs the ordering, never the results.
    ranked = Reranker(ScriptedClient(error=RuntimeError("down")),
                      log=lambda _: None)("q", _hits(4))
    assert [h.chunk_id for h in ranked] == original


def test_a_transient_empty_reply_is_retried_before_giving_up():
    """The server intermittently returns nothing; one retry beats losing the rank."""
    from rag.reranking import Reranker

    class Flaky(ScriptedClient):
        def complete(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("Empty reply (finish_reason='stop')")
            return "2"

    client = Flaky()
    ranked = Reranker(client, log=lambda _: None)("q", _hits(3))
    assert client.calls == 2, "the first failure should be retried"
    assert ranked[0].chunk_id == "c1", "the retry's ranking is used"

    # Twice is the limit — a server that is properly down must not be hammered.
    down = ScriptedClient(error=RuntimeError("down"))
    Reranker(down, log=lambda _: None)("q", _hits(3))
    assert down.calls == 2, down.calls


def test_ranking_parser_ignores_repeats_and_out_of_range():
    from rag.reranking import parse_ranking

    assert parse_ranking("2, 1, 2, 3", 3) == [1, 0, 2], "a repeat is not a new pick"
    assert parse_ranking("[3] then [1]", 3) == [2, 0], "numbers in any wrapping"
    assert parse_ranking("7, 2", 3) == [1], "an invented number names no passage"
    assert parse_ranking("", 3) == []


def test_rerank_happens_before_the_cut_to_top_k():
    """Ranking only what dense already preferred would defeat the point."""
    from rag.reranking import Reranker

    with tempfile.TemporaryDirectory() as tmp:
        index = VectorIndex(HashEmbedder(), db_path=tmp, collection_name="rerank")
        index.add([Chunk(index=i, text=f"creatine passage number {i} about energy",
                         section=f"s{i}") for i in range(8)])
        seen = {}

        class Capturing(ScriptedClient):
            def complete(self, **kwargs):
                seen["prompt"] = kwargs["prompt"]
                return super().complete(**kwargs)

        client = Capturing(reply="6")
        retriever = Retriever(index, top_k=2,
                              reranker=Reranker(client, log=lambda _: None),
                              rerank_candidates=6)
        results = retriever("creatine energy")
        assert len(results) == 2, "still cut to top_k after ranking"
        assert seen["prompt"].count("] (") >= 3, "the model saw more than top_k"
        assert [h.rank for h in results] == [1, 2]


def test_reranking_is_query_time_and_needs_no_rebuild():
    settings = Settings()
    assert settings.collection_name == settings.with_(rerank_candidates=5).collection_name
    assert settings.reader_key == settings.with_(rerank_candidates=5).reader_key
    # The switch collapses into the count, the same way the other stages do.
    assert Settings(enable_rerank=False).rerank_candidates == 0


if __name__ == "__main__":
    failures = 0
    for name, test in sorted(globals().items()):
        if name.startswith("test_") and callable(test):
            try:
                test()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {type(exc).__name__}: {exc}")
    print(f"\n{'all tests passed' if not failures else f'{failures} failure(s)'}")
    sys.exit(1 if failures else 0)
