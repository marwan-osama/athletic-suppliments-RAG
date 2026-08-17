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

from rag.augmentation import QuestionGenerator, parse_questions
from rag.chunking import MarkdownChunker
from rag.config import DOCUMENT_PREFIX, QUERY_PREFIX, Settings, env_flag
from rag.diagnostics import LINK_HEAVY, OVERSIZED, TINY, ChunkInspector
from rag.embedding import HashEmbedder, ServerEmbedder, _normalize
from rag.indexing import VectorIndex
from rag.llm import LLMClient, LLMError, RateLimiter
from rag.preprocessing import MarkdownCleaner
from rag.retrieval import Retriever
from rag.schema import Chunk, Stage

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
