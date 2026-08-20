# Athletic supplements RAG

Retrieval over the NIH ODS fact sheet *Dietary Supplements for Exercise and
Athletic Performance*, refactored out of a single notebook into one class per
pipeline stage, plus a Streamlit UI for tuning the retrieval settings and
reviewing what comes back.

```
read PDF → clean → chunk → generate questions → embed → index
query → expand → retrieve → answer (cited to the page)
```

The source document is a PDF, and every answer names the page each claim came
from — `[1, p. 19]`, not just `[1]`. See [Page citations](#page-citations).

Models run locally in [LM Studio](https://lmstudio.ai), both off its
OpenAI-compatible server at `http://127.0.0.1:1234/v1` — no key, no quota:

| | model | notes |
| --- | --- | --- |
| embeddings | `text-embedding-embeddinggemma-300m` | 768 dims, already unit-normalized, asymmetric (see below) |
| generation | `openai/gpt-oss-20b` | ~1s per question-generation call, barely reasons (see below) |

Nothing is tied to LM Studio beyond the defaults — point `LLM_BASE_URL` at any
OpenAI-shaped endpoint and set `LLM_API_KEY` if it needs one.

**Generation and embeddings are separately addressable.** `EMBED_BASE_URL`
splits the embedder off `LLM_BASE_URL`, which is what a hosted gateway requires:
OpenRouter serves `/chat/completions` and no `/embeddings`. It is also what
keeps an index usable — the vectors in `chroma_db` came from one embedding
model, so the embedder has to stay where that model runs even when generation
moves. To run generation, reranking and the ragas judge on OpenRouter against
the index already on disk:

```
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_API_KEY=...
LLM_MODEL=openai/gpt-oss-20b
EMBED_BASE_URL=http://127.0.0.1:1234/v1
LLM_RPM=60
```

Keeping `LLM_MODEL` at the id LM Studio served leaves runs comparable across
hosts. `EMBED_BASE_URL` is not part of the collection name — the same model at a
different hostname produces the same vectors — so no rebuild is triggered.

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
| [rag/fetching.py](rag/fetching.py) | `PdfReader` | PDF → markdown with page markers, cached on disk |
| [rag/preprocessing.py](rag/preprocessing.py) | `MarkdownCleaner` | strips citation links, nav chrome, HTML remnants, the reference list |
| [rag/chunking.py](rag/chunking.py) | `MarkdownChunker` | heading-aware split; each chunk carries its heading path |
| [rag/augmentation.py](rag/augmentation.py) | `QuestionGenerator` | hypothetical questions per chunk, generated in parallel |
| [rag/llm.py](rag/llm.py) | `LLMClient` | the only module that calls the server: retries, pacing, errors |
| [rag/embedding.py](rag/embedding.py) | `ServerEmbedder`, `HashEmbedder` | query/document-aware embeddings; offline fallback |
| [rag/indexing.py](rag/indexing.py) | `VectorIndex` | ChromaDB collection: upsert, count, query, reset |
| [rag/expansion.py](rag/expansion.py) | `QueryExpander` | query → that query plus other phrasings (optional) |
| [rag/retrieval.py](rag/retrieval.py) | `Retriever` | query → ranked chunks, one result per parent chunk, phrasings merged |
| [rag/answering.py](rag/answering.py) | `Answerer` | grounded answer with `[n, p. X]` citations (optional) |
| [rag/diagnostics.py](rag/diagnostics.py) | `ChunkInspector` | chunk size stats and quality flags |
| [rag/pipeline.py](rag/pipeline.py) | `RAGPipeline` | wires the stages; `build()`, `search()`, `answer()` |
| [rag/config.py](rag/config.py) | `Settings` | every tunable value, one dataclass |
| [evaluation/](evaluation) | `EvaluationEngine` | grades the pipeline against a golden set (optional) |
| [app.py](app.py) | — | Streamlit UI |
| [rag/cli.py](rag/cli.py) | — | `python -m rag.cli chunks \| build \| query` |
| [tools/build_source_pdf.py](tools/build_source_pdf.py) | — | typesets the fact sheet into the PDF under `data/` |

Each stage is a callable object and composes with `|`:

```python
chunks = (PdfReader() | MarkdownCleaner() | MarkdownChunker(600, 100))(source)
```

## Setup

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Then put your key in `.env` (see [.env.example](.env.example)):

In LM Studio: load both models, open **Developer → Local Server** and start it.
Then `cp .env.example .env` — for a purely local setup the defaults already match,
so the file only needs `RAG_SOURCE` if you want to index a different PDF.

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

## Page citations

The source is a PDF and every answer says which page it drew on:

```
Loading is 20 g/day of creatine monohydrate in four portions of 5 g [1, p. 19].
```

Getting there takes two things a PDF does not hand you.

**Structure.** A PDF has no headings, no paragraphs and no reading order — only
glyphs at coordinates. `PdfReader` recovers what the rest of the pipeline needs
from the one structural signal that survives into the file: the distinct font
sizes above the body size are ranked and mapped onto heading levels 1..N, which
hands `MarkdownChunker` the `#` marks it already splits on. That is what keeps
`Creatine > Efficacy` breadcrumbs working. Paragraphs are rejoined by noticing
which lines stop short of the right margin, and running heads are dropped by
position — a line that repeats *and* sits in the page margin, since "Efficacy"
repeats under twenty-odd ingredients and is a heading, not a running head.

**Provenance.** Each page's text is preceded by a `<!--page:N-->` marker. It is
an HTML comment on purpose: `MarkdownCleaner` rewrites almost every other
character but matches none of its patterns against `<!-- -->`, so the marker
reaches `MarkdownChunker`, which reads it, records the page(s) on the chunk, and
strips it before anything is indexed. A chunk that straddles a break carries both
pages (`pp. 4-5`); most chunks contain no marker at all and take the page last
opened, which is why tracking is sequential rather than per-chunk.

From there the page rides in Chroma metadata (as a scalar `"4,5"` — Chroma stores
no sequences) onto `Retrieved.pages`, and the `Answerer` labels every source with
it before the model ever sees it.

The last step is the one worth arguing about. The prompt asks for `[1, p. 19]`,
but asking is not enough: a small model writes a bare `[3]`, or a page it liked
the look of. So the citations it returns are **rewritten against the index**
afterwards — the page of source *n* is something `Answerer` already knows, and
looking it up beats trusting the model to copy it. The model chooses which source
supports a claim; the page that source came from is not its to invent. A citation
pointing at a source that does not exist is left exactly as it is, because
quietly renumbering it would hide the model inventing a source.

Spot-checked by pulling the cited page out of the PDF and confirming the text is
on it: 15 of 15 citations correct across five questions.

### Where the PDF comes from

ODS publishes this fact sheet as a web page only — every PDF linked from it is a
cited reference, not the fact sheet. So the document is typeset from the page by
[tools/build_source_pdf.py](tools/build_source_pdf.py) and checked in at
`data/ods-exercise-and-athletic-performance.pdf` (32 pages):

```bash
.venv/bin/python tools/build_source_pdf.py
```

Point `RAG_SOURCE` at any other PDF to index it instead. A different source gets
its own collection, so two documents can never end up sharing one index.

## Streamlit UI

```bash
.venv/bin/streamlit run app.py
```

- **Sidebar** — one section per stage, in the order the stages run, holding
  every hyperparameter that stage takes. Each optional stage has a switch that
  bypasses it: **Cleaning** (chunk the raw extraction), **Question
  augmentation**, **Answering**, the extraction cache under **Source &
  fetching**, and the model server itself under **Embedding** (which falls back
  to offline hash vectors). Build / rebuild the index from here, and reset every
  control to its defaults with one button.

  | section | what it holds |
  | --- | --- |
  | 📥 Source & fetching | source, base URL, cache directory, cache switch, minimum extraction size |
  | 🧹 Cleaning | master switch, link unwrapping, citation markers, navigation lines, heading naming, dropped sections |
  | ✂️ Chunking | size, overlap, fragment-merge threshold, heading prefix, heading path cap |
  | ❓ Question augmentation | master switch, questions per chunk, workers, temperature, max tokens |
  | 🔢 Embedding | server switch, model, batch size, dimensions, document and query prefixes |
  | 🗄️ Index storage | Chroma path, collection prefix, rows per upsert |
  | 🔀 Query expansion | master switch, extra phrasings, temperature, max tokens, agreement boost and its cap |
  | 🔎 Retrieval | top-k, one-result-per-chunk, overfetch multiplier |
  | 💬 Answering | master switch, temperature, max tokens, context budget |
  | 🔌 Model server | base URL, generation model, API key, rate limit, timeout, retries, reasoning effort |
  | 🩺 Chunk diagnostics | the TINY flag threshold |
  | 📊 Evaluation | golden set, report directory, failure threshold, judge model/embeddings/endpoint, acronym expansion, LLM diagnosis, concurrency, timeout |
- **Ask** — ask a question, or keep a question set and run one (or all) of them.
  Every result shows its similarity, whether it matched the chunk or a generated
  question, its heading path, and its full text.
- **Chunks** — the chunks the current settings produce, *before* paying for any
  embeddings: size stats, quality flags, text filter, and the projected number of
  embeddings. This is the cheap way to tune chunk size and overlap.
- **Review** — mark retrieved chunks relevant / not relevant with notes, see
  precision per question, and export the judgements as JSON.
- **Evaluate** — score the pipeline against the golden set: four metrics, a
  per-question table, what to try for each failure, and the JSON report.
- **Index** — row counts by type, collection list, the stages currently in
  force, the effective settings (with what differs from the defaults called out),
  and the pipeline log.

Everything that changes the vectors is part of the collection name
(`ods_health_facts__embeddinggem_c600_o100_q3_m80_s1` — embedder, chunk size,
overlap, questions, merge threshold, heading prefix), so moving a slider builds a
separate index instead of colliding with the previous one, and moving it back
reuses the index you already built. Settings that arrived after that scheme —
the cleaning flags, the heading cap, the embedding prefixes — are hashed into an
`_x…` suffix, which stays empty while they are all at their defaults so indexes
already on disk keep their names.

### Query expansion

Retrieval can search more than the question as typed. With it on, the model is
asked for a few other phrasings — domain terms, scientific synonyms — and the
index is searched once per phrasing, which finds passages worded unlike the
question. A chunk that several phrasings agree on is more likely to be the right
one, so extra agreement lifts it up the ranking.

That bonus lands on `Retrieved.score`, which is what results are sorted by.
`Retrieved.similarity` stays exactly what the embedder returned, so the number
shown next to a result never overstates the match; a boosted result says how many
phrasings agreed and what it was given. Agreement is counted one vote per
phrasing, not per matching row — a chunk found through three of its own
hypothetical questions is one phrasing agreeing with itself, not three
confirmations.

It costs one generation call per **search** (build time is unaffected), so
searching gets slower. `RAG_ENABLE_QUERY_EXPANSION=false`, or the sidebar toggle,
turns it off.

Settings split in two: those that decide what is stored (`Settings.index_key`)
get a pipeline and a collection of their own, and everything else is pushed onto
the live stages by `RAGPipeline.apply()` — so changing top-k or a temperature
never reopens the database or invalidates an index.

## Evaluation

Judging retrieval by eye stops scaling around the third question. The
`evaluation` package asks the pipeline a fixed set of questions and grades what
comes back:

| metric | grades | asks |
| --- | --- | --- |
| context recall | `Retriever` | did it find the evidence the reference answer needs? |
| context precision | `Retriever` | are the chunks it returned actually about the question? |
| faithfulness | `Answerer` | is the answer grounded in those chunks? |
| answer relevancy | `Answerer` | does the answer address the question asked? |

Two grade retrieval and two grade generation, so a failing metric names the
stage to look at rather than saying "the RAG is bad".

```bash
.venv/bin/python -m evaluation run
```

The golden file holds only the **question** and a **reference answer**. The
contexts and the answer come from `RAGPipeline.search()` and `.answer()` at run
time — see [evaluation/harness.py](evaluation/harness.py). That is what makes
the numbers worth having: they move when the pipeline changes. Measured against
the local models over all 34 questions, with only `top_k` varying:

| `top_k` | context recall | context precision | faithfulness | answer relevancy |
| --- | --- | --- | --- | --- |
| 5 | 0.628 | **0.793** | 0.770 | **0.736** |
| 10 *(default)* | **0.781** | 0.714 | **0.786** | 0.688 |

which is the recall/precision trade-off the knob actually buys, and why the
default is 10: evidence that is never retrieved cannot be cited, whereas a chunk
that is retrieved and unused costs little. Depth is what the multi-part and
comparative questions need — at `top_k=5` several of them were finding the right
chunks and ranking them below the cutoff, so *"HMB or BCAAs for recovery"*,
*"tart cherry or quercetin"* and the three-supplement cyclist question all go
from around 0.55 recall to 1.00 simply by looking further down the list.

Three of the 34 questions are ones the page cannot answer, and they score
faithfulness 0.00 by construction — "the page does not cover this" is a claim no
retrieved chunk can support. Excluding them, `top_k=10` gives context recall
0.822 and faithfulness 0.862, both above the 0.8 threshold, against context
precision 0.739 and answer relevancy 0.742.

The set is 34 questions, and most of them are there to break something in
particular. Beyond the plain single-section lookups it carries multi-hop
questions whose answer lives in two ingredient sections at once (vegetarians on
creatine *and* iron); near-miss pairs the retriever is likely to confuse
(arginine against citrulline, both vasodilators; beta-alanine against sodium
bicarbonate, both buffers; tart cherry against quercetin, one of which contains
the other); a false-premise question that a helpful model will happily answer
anyway (a DHEA dose, when the page says DHEA does nothing); a negation question
that wants the ingredients with *no* evidence behind them; terse keyword queries
and a misspelled one; a query whose only handle is an acronym; and three
questions the page cannot answer, whose reference answers say so and then say
what the page does cover instead. Those last ones are the cheap check on
groundedness — a pipeline that invents a carbohydrate-loading protocol fails
them loudly.

Scoring uses [ragas](https://github.com/explodinggradients/ragas), imported only
when a run starts, so the pipeline, the CLI and the rest of the UI never need
it. Install it with `pip install -r requirements.txt`; without it the Evaluate
tab says so and stays disabled. The judge defaults to the same local server —
`eval_llm_model` / `eval_base_url` point it at a stronger or hosted model.

Every claim in a reference answer is traceable to the source page, which is
what makes context recall mean anything: the metric asks whether retrieval found
the evidence the reference relies on, so a reference asserting something the
corpus does not contain fails for reasons that have nothing to do with
retrieval. Keep that property when adding questions.

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

Same document, same chunk size and overlap (600/100). The "here" column was
measured on the HTML extraction the notebook also read; the PDF the pipeline now
indexes gives 286 chunks over the same 95 sections, with the same flag counts:

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
- **Empty headings are given names.** A heading can arrive with no text of its
  own — a glyph the extractor could not map, or a name set as an image. The
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
