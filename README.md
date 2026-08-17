# Athletic supplements RAG

Retrieval over the NIH ODS fact sheet *Dietary Supplements for Exercise and
Athletic Performance*, refactored out of a single notebook into one class per
pipeline stage, plus a Streamlit UI for tuning the retrieval settings and
reviewing what comes back.

```
fetch → clean → chunk → generate questions → embed → index → retrieve → answer
```

Models run locally in [LM Studio](https://lmstudio.ai), both off its
OpenAI-compatible server at `http://127.0.0.1:1234/v1` — no key, no quota:

| | model | notes |
| --- | --- | --- |
| embeddings | `text-embedding-embeddinggemma-300m` | 768 dims, already unit-normalized, asymmetric (see below) |
| generation | `openai/gpt-oss-20b` | ~1s per question-generation call, barely reasons (see below) |

Nothing is tied to LM Studio beyond the defaults — point `LLM_BASE_URL` at any
OpenAI-shaped endpoint and set `LLM_API_KEY` if it needs one.

**The embedding model is asymmetric**, and its own instruction templates measurably
beat the alternatives. On a creatine query scored against a matching and a
mismatched passage:

| prefixes | sim(match) | sim(mismatch) | margin |
| --- | --- | --- | --- |
| none | 0.698 | 0.352 | 0.346 |
| generic `query:` / `passage:` | 0.753 | 0.391 | 0.361 |
| **EmbeddingGemma templates** | 0.727 | 0.257 | **0.470** |

So documents are embedded as `title: none | text: …` and searches as
`task: search result | query: …`. Both live in [config.py](rag/config.py); set
them to `""` for a symmetric model.

**Reasoning tokens come out of `max_tokens`.** `gpt-oss-20b` barely reasons on
these prompts — about 9 tokens — so the budgets (1024 for question generation,
2048 for answers) are generous. Other models are not so cheap: `gemma-4-e2b`
spends ~390 tokens thinking and ignores both `reasoning: {"effort": "none"}` and
`chat_template_kwargs: {"enable_thinking": false}`, which at a small budget makes
the reply arrive with empty content and `finish_reason: "length"` — exactly like
a model with nothing to say. [llm.py](rag/llm.py) raises on an empty reply rather
than passing it off as a valid answer, so if you swap the model and questions
stop appearing, the log will say why.

## Layout

| File | Class | Does |
| --- | --- | --- |
| [rag/fetching.py](rag/fetching.py) | `SourceFetcher` | HTML file or URL → markdown (trafilatura), cached on disk |
| [rag/preprocessing.py](rag/preprocessing.py) | `MarkdownCleaner` | strips citation links, nav chrome, HTML remnants, the reference list |
| [rag/chunking.py](rag/chunking.py) | `MarkdownChunker` | heading-aware split; each chunk carries its heading path |
| [rag/augmentation.py](rag/augmentation.py) | `QuestionGenerator` | hypothetical questions per chunk, generated in parallel |
| [rag/llm.py](rag/llm.py) | `LLMClient` | the only module that calls the server: retries, pacing, errors |
| [rag/embedding.py](rag/embedding.py) | `ServerEmbedder`, `HashEmbedder` | query/document-aware embeddings; offline fallback |
| [rag/indexing.py](rag/indexing.py) | `VectorIndex` | ChromaDB collection: upsert, count, query, reset |
| [rag/retrieval.py](rag/retrieval.py) | `Retriever` | query → ranked chunks, one result per parent chunk |
| [rag/answering.py](rag/answering.py) | `Answerer` | grounded answer with `[n]` citations (optional) |
| [rag/diagnostics.py](rag/diagnostics.py) | `ChunkInspector` | chunk size stats and quality flags |
| [rag/pipeline.py](rag/pipeline.py) | `RAGPipeline` | wires the stages; `build()`, `search()`, `answer()` |
| [rag/config.py](rag/config.py) | `Settings` | every tunable value, one dataclass |
| [app.py](app.py) | — | Streamlit UI |
| [rag/cli.py](rag/cli.py) | — | `python -m rag.cli chunks \| build \| query` |

Each stage is a callable object and composes with `|`:

```python
chunks = (SourceFetcher() | MarkdownCleaner() | MarkdownChunker(600, 100))(source)
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Then put your key in `.env` (see [.env.example](.env.example)):

In LM Studio: load both models, open **Developer → Local Server** and start it.
Then `cp .env.example .env` — for a purely local setup the defaults already match,
so the file only needs `RAG_SOURCE` if you want to point at a saved copy of the
page.

With `RAG_OFFLINE=true`, or with the server stopped, `HashEmbedder`
(word-overlap vectors) keeps the UI and tests runnable — retrieval quality is poor
and there is no generation.

### How long a build takes

Everything is local, so the only budget is time. Measured on this machine at the
default 600/100 chunking:

| | calls | wall clock |
| --- | --- | --- |
| embeddings only (`RAG_ENABLE_QUESTIONS=false`) | 18 | **8 s** |
| with 3 questions per chunk | 72 + 288 | **~4 min** |

Generation is the bulk of it: ~1 s per call, ~0.9 s per chunk with the default 8
workers. Both numbers are model-specific — `gemma-4-e2b` took 49 minutes for the
same build — so the constants in [pipeline.py](rag/pipeline.py) are worth
re-measuring after a swap. The Chunks tab shows the estimate for whatever
settings you have picked, before you start.

To skip it entirely, in `.env`:

```
RAG_ENABLE_QUESTIONS=false
```

That switch is the master control (`enable_questions` in
[config.py](rag/config.py)). It overrides the per-chunk count wherever that comes
from, including the UI slider and `--questions`, and disabled runs get their own
`_q0_` collection so the two indexes never mix.

## Streamlit UI

```bash
.venv/bin/streamlit run app.py
```

- **Sidebar** — source, chunk size, overlap, fragment-merge threshold, heading
  prefix, top-k, one-result-per-chunk, questions per chunk. Build / rebuild the
  index from here.
- **Ask** — ask a question, or keep a question set and run one (or all) of them.
  Every result shows its similarity, whether it matched the chunk or a generated
  question, its heading path, and its full text.
- **Chunks** — the chunks the current settings produce, *before* paying for any
  embeddings: size stats, quality flags, text filter, and the projected number of
  embeddings. This is the cheap way to tune chunk size and overlap.
- **Review** — mark retrieved chunks relevant / not relevant with notes, see
  precision per question, and export the judgements as JSON.
- **Index** — row counts by type, collection list, pipeline log.

Everything that changes the vectors is part of the collection name
(`ods_health_facts__gem_c600_o100_q3_m80_s1` — embedder, chunk size, overlap,
questions, merge threshold, heading prefix), so moving a slider builds a separate
index instead of colliding with the previous one, and moving it back reuses the
index you already built.

## CLI

```bash
.venv/bin/python -m rag.cli chunks --dump chunks_dump.md   # free: no API calls
```

```bash
.venv/bin/python -m rag.cli build --chunk-size 600 --chunk-overlap 100
```

```bash
.venv/bin/python -m rag.cli query "Does creatine improve athletic performance?" --answer
```

## Tests

```bash
.venv/bin/python tests/test_pipeline.py
```

All offline — nothing needs to be running: cleaning, chunking, id stability, stage
composition, diagnostics, an end-to-end index-and-retrieve round trip against a
temporary ChromaDB, and the server contract (payload shape, instruction prefixes,
ordering by `index`, auth header only when a key is set, 429 retry, 400 not
retried, empty-reply detection, unreachable-server message) against a mock HTTP
transport.

## Notes on the refactor

Same source file, same chunk size and overlap (600/100):

| | notebook | here |
| --- | --- | --- |
| chunks | 463 | **288** |
| smallest chunk | 3 chars | **111 chars** |
| under 100 chars | 35 | **0** |
| link-only / no-prose | many | **0** |
| flagged as suspect | 43 | **1** (a real table) |
| embeddings at 3 questions/chunk | 1,842 | **1,152** |

Fewer, larger, cleaner chunks covering the same content — 37% fewer embeddings to
pay for, and nothing in the index that is only URLs or a bare heading.

Behavioural changes, all of them deliberate:

- **Cleaning step added.** In the original output whole chunks consisted of
  citation URLs (`LINK-HEAVY`), and 35 chunks were under 100 characters — mostly
  bare headings like `#### Efficacy`. Links, citation markers, `<sub>` tags, nav
  lines and the reference list are removed before chunking.
- **Empty headings are given names.** Every supplement heading on this page
  extracts as a bare `### ` — trafilatura drops the element holding the name. The
  name is recovered from the first sentence of the section ("HMB is a metabolite
  of…" → `HMB`), which takes the number of distinct sections from 15 to 95.
  Without it, 190 of 288 chunks were labelled only "Efficacy" or "Implications
  for use", with nothing saying which supplement they described.
- **Heading-aware chunking.** Chunks are cut at headings and prefixed with their
  heading path (`Creatine > Efficacy`), so no chunk mixes two supplements, no
  chunk is a lone heading, and every chunk states its own subject.
- **Content-derived chunk ids** (`c0042-1f3a9b7c`) instead of `uuid4`, so
  re-indexing the same document upserts instead of duplicating.
- **Questions point at their parent** rather than storing a copy of the chunk
  text in metadata; the parent text is resolved at query time in one call.
- **Results are collapsed per chunk**, so one passage can't fill every top-k slot
  through its own generated questions.
- **Question generation is parallel** (thread pool) instead of one call at a time,
  bounded by the rate limiter rather than by the pool size.
- **Chunking is separable from indexing**, so chunk size and overlap can be tuned
  in the UI (or via `rag.cli chunks`) without spending anything on embeddings.
- **One server, one client.** `LLMClient` is the only code that makes a request,
  so retries, pacing and error reporting exist once — and swapping providers is a
  change of `base_url` and two model ids. The pipeline has run on Gemini, then
  OpenRouter, now LM Studio; only [config.py](rag/config.py) really moved.
- **Instruction prefixes instead of a task parameter.** Gemini had `task_type`;
  OpenAI-shaped `/embeddings` has no such field, so the query/document
  instructions are prepended to the text (see the table above).
- **Config comes from the environment.** The notebook had a Gemini API key inline
  — if that key is still live, revoke it at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey). An OpenRouter
  key was used later in development; that one is worth rotating too.

Extracted markdown is cached in `.cache/`, so only the first run reads the source;
the index lives in `./chroma_db`. Both are gitignored.
