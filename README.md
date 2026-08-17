# Athletic supplements RAG

Retrieval over the NIH ODS fact sheet *Dietary Supplements for Exercise and
Athletic Performance*, refactored out of a single notebook into one class per
pipeline stage, plus a Streamlit UI for tuning the retrieval settings and
reviewing what comes back.

```
fetch → clean → chunk → generate questions → embed → index → retrieve → answer
```

Models, both through OpenRouter on one API key:

| | model | notes |
| --- | --- | --- |
| embeddings | `nvidia/llama-nemotron-embed-vl-1b-v2:free` | 2048 dims, asymmetric (`query:` / `passage:` prefixes) |
| generation | `nvidia/nemotron-nano-9b-v2:free` | 128k context, reasons on every call (see below) |

**Reasoning eats the token budget.** This model ignores
`reasoning: {"effort": "none"}` — it still reports reasoning tokens — and those
tokens are charged against `max_tokens`. Ask for too few and the reply arrives as
`content: null` with `finish_reason: "length"`, which looks exactly like a model
with nothing to say. Hence the generous budgets (1024 for question generation,
2048 for answers), and [openrouter.py](rag/openrouter.py) raises on an empty reply
instead of passing it off as a valid, empty answer.

## Layout

| File | Class | Does |
| --- | --- | --- |
| [rag/fetching.py](rag/fetching.py) | `SourceFetcher` | HTML file or URL → markdown (trafilatura), cached on disk |
| [rag/preprocessing.py](rag/preprocessing.py) | `MarkdownCleaner` | strips citation links, nav chrome, HTML remnants, the reference list |
| [rag/chunking.py](rag/chunking.py) | `MarkdownChunker` | heading-aware split; each chunk carries its heading path |
| [rag/augmentation.py](rag/augmentation.py) | `QuestionGenerator` | hypothetical questions per chunk, generated in parallel |
| [rag/openrouter.py](rag/openrouter.py) | `OpenRouterClient` | the only module that calls the API: retries, rate limiting, errors |
| [rag/embedding.py](rag/embedding.py) | `OpenRouterEmbedder`, `HashEmbedder` | query/passage-aware embeddings; offline fallback |
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

```bash
cp .env.example .env   # then edit: OPENROUTER_API_KEY=...
```

Get a key at [openrouter.ai/keys](https://openrouter.ai/keys). Without one
everything still runs, using `HashEmbedder` (word-overlap vectors) so you can
exercise the UI offline — retrieval quality is poor and there is no answer
generation.

### Free-tier pacing

`:free` variants allow roughly 20 requests/minute plus a daily cap (which depends
on whether you have ever bought credits), so [openrouter.py](rag/openrouter.py)
paces every request — `requests_per_minute` in [config.py](rag/config.py) — and
honours `Retry-After` on a 429. At the default 600/100 chunking that is:

| | requests | at 20/min |
| --- | --- | --- |
| embeddings only (`--questions 0`) | 18 | ~1 min |
| with 3 questions per chunk | 360 | ~18 min |

The Chunks tab shows this estimate for whatever settings you have picked, before
you spend anything. If the daily cap is your constraint, turn question generation
off in `.env` — the pipeline works fine on chunk rows alone:

```
RAG_ENABLE_QUESTIONS=false
```

That switch is the master control (`enable_questions` in
[config.py](rag/config.py)). It overrides the per-chunk count wherever that comes
from, including the UI slider and `--questions`, and disabled runs get their own
`_q0_` collection so the two indexes never mix.

Note that free variants log prompts and outputs to the provider for training —
that includes the questions you type into the UI.

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

All offline, no key needed: cleaning, chunking, id stability, stage composition,
diagnostics, an end-to-end index-and-retrieve round trip against a temporary
ChromaDB, and the OpenRouter request/response contract (payload shape,
`query:`/`passage:` prefixes, ordering by `index`, 429 retry, 400 not retried,
`<think>` stripping) against a mock HTTP transport.

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
- **One provider, one client.** Gemini is gone; `OpenRouterClient` is the only
  code that makes a request, so retries, pacing and error reporting exist once.
- **Query/passage prefixes.** The old embedder used Gemini's `task_type`; this
  model expects `query:` on searches and `passage:` on documents instead. Both are
  in [config.py](rag/config.py) — set them to `""` for a symmetric model.
- **Config comes from the environment.** The notebook had a Gemini API key inline
  — if that key is still live, revoke it at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

Extracted markdown is cached in `.cache/`, so only the first run reads the source;
the index lives in `./chroma_db`. Both are gitignored.
