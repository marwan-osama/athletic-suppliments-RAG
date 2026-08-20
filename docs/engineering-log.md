# Engineering log — golden set, PDF migration, page citations, evaluation

Working record of what was built, what went wrong, and what the numbers came out
at. Written to be quoted from later: every hurdle has an ID (`H1`–`H17`), every
figure below was measured rather than estimated, and the commands that produced
them are given so a claim can be re-checked before it goes on a slide.

Session date: 2026-08-20. Branch: `feat/lm-studio-local-models`.

---

## 1. Scope

Four pieces of work, in order:

1. **Golden evaluation set expanded** from 3 questions to 34, built around edge
   cases the original set could not exercise.
2. **Pipeline input switched from an HTML page to a PDF**, and page provenance
   threaded through every stage so answers cite the page they came from.
3. **Evaluation run, a defect found and fixed, and the run repeated** to measure
   whether the fix worked.
4. **Retrieval depth measured and re-set** — `top_k` raised from 5 to 10 on the
   strength of that measurement.

Files changed: 18, plus new `data/` (the source PDF) and `tools/` (its
generator). Tests: 45 pipeline + 11 evaluation = **56 passing**.

---

## 2. Hurdles

Each entry: what was observed, why it mattered, and how it was resolved. **Kind**
distinguishes problems that came from outside the project from defects in the
code — including the ones this work introduced.

### External and environmental

#### H1 — The PDF the work was premised on does not exist
**Kind:** external · **Status:** worked around

The plan was to index the official NIH ODS fact sheet as a PDF. ODS publishes
that fact sheet as a **web page only**. Enumerating every PDF link on the page
returned 29 URLs, all of them cited references (NCAA, WADA, NFHS, ACSM, HPRC),
none the fact sheet itself.

```js
[...document.querySelectorAll('a')].map(a => a.href).filter(h => /\.pdf/i.test(h))
```

**Resolution:** the source document is typeset from the same extraction the
pipeline previously read, by `tools/build_source_pdf.py`, and checked in at
`data/ods-exercise-and-athletic-performance.pdf`. Any other PDF can be indexed
by pointing `RAG_SOURCE` at it.

**Presentation angle:** a requirement that looked settled ("use the real PDF")
turned out to be unsatisfiable, and was only discovered by going and looking.

#### H2 — Cloudflare bot challenge blocked automated fetching
**Kind:** external · **Status:** worked around

`curl` against `ods.od.nih.gov` returned HTTP 403 with a `Just a moment...`
interstitial — a Cloudflare JS challenge — for every URL including the fact
sheet itself. A browser user-agent header did not change the result.

**Resolution:** loaded the page in a real browser, which passed the challenge
normally. No attempt was made to defeat the challenge programmatically.

#### H3 — No PDF renderer available on the machine
**Kind:** environmental · **Status:** resolved

With no NIH PDF to download, the fallback was to render the page to PDF. None of
Chrome, Edge, `wkhtmltopdf`, `weasyprint` or `pandoc` was installed, and no
Python PDF writer was present.

**Resolution:** installed `reportlab` (BSD) for typesetting and `pdfplumber`
(MIT) for extraction. `pdfplumber` was chosen over PyMuPDF specifically because
it exposes per-character font size — which H4 turned out to require — without
PyMuPDF's AGPL licensing.

#### H4 — A PDF carries no headings, and the pipeline depends on them
**Kind:** design constraint · **Status:** resolved

The chunker splits on markdown headings and stamps each chunk with its heading
path (`Creatine > Efficacy`). Those breadcrumbs are load-bearing for retrieval
quality and for the whole golden set. A PDF has no headings — only glyphs at
coordinates.

**Resolution:** `PdfReader` recovers structure from the one signal that survives
into the file. Distinct font sizes above the body size are ranked and mapped onto
heading levels 1..N; paragraphs are rejoined by detecting lines that stop short
of the right margin. Nothing is hard-coded to this document's sizes.

### Extraction defects (introduced by this work)

#### H5 — Running-head detection deleted real headings
**Kind:** defect (introduced) · **Status:** fixed

First implementation dropped short lines that repeated across most pages, on the
theory that those are running heads. In this document "Efficacy", "Safety" and
"Implications for use" head a subsection under each of ~21 ingredients, so they
repeat on most pages — and were deleted.

**Symptom:** 36 headings recovered where the source has 95. Section breadcrumbs
collapsed, which would have degraded every retrieval.

**Fix:** a running head is now defined by **position as well as repetition** — it
must repeat *and* sit in the top or bottom 8% of the page (`MARGIN_BAND`).

**Evidence:** headings recovered went 36 → **95**, matching the source structure.

#### H6 — Headings that wrap became two headings
**Kind:** defect (introduced) · **Status:** fixed

The document title spans two lines in the PDF. Each line was emitted as its own
heading, splitting the document at a half-title:

```
# Dietary Supplements for Exercise and Athletic
# Performance
```

**Fix:** a heading line immediately following another heading of the same level
is joined onto it.

#### H7 — Bullet glyphs arrived as `(cid:127)`
**Kind:** defect (introduced) · **Status:** fixed

`pdfminer` emits `(cid:N)` for glyphs it cannot map to Unicode. The symbol-font
bullet came through as literal `(cid:127)` text, so list items were not detected
as list items and the marker text entered the index.

**Fix:** `_decode_glyphs()` maps the known bullet cids to `•` and strips the
rest; bullet detection widened to a set of glyphs.

#### H8 — A stale cache was served as PDF output
**Kind:** defect (introduced; inherited shape) · **Status:** fixed

`PdfReader.run()` checked its on-disk cache **before** validating that the source
was a PDF — the ordering carried over from the HTML fetcher it replaced. The
`.env` file still pointed `RAG_SOURCE` at the old HTML file, whose cache entry
existed, so the reader happily returned HTML-derived markdown with no page
markers in it.

**Symptom:** all 288 chunks had zero page numbers, with no error anywhere. Cost
roughly 20 minutes of misdirected debugging.

**Fix:** the source extension is validated **before** the cache is consulted. A
regression test (`test_a_source_that_is_not_a_pdf_is_refused_before_the_cache`)
plants a stale cache entry and asserts the reader still refuses.

**Presentation angle:** the most expensive failures are the silent ones. Nothing
raised; the pipeline just produced quietly wrong output.

#### H9 — Two different documents would share one index
**Kind:** latent defect (pre-existing) · **Status:** fixed

`Settings.collection_name` did not include `source`. Pointing `RAG_SOURCE` at a
different document therefore reused the previous document's ChromaDB collection.
Pre-existing, but H8 is exactly the failure it enables, so it was fixed here.

**Fix:** `source` added to `VARIANT_FIELDS`. The default document keeps the clean
collection name; any other source gets its own hash suffix.

### Tooling and process

#### H10 — Shell history expansion produced a false debugging signal
**Kind:** environmental · **Status:** understood

While debugging H8, a check for page markers reported **0 markers** in a file
that demonstrably contained 32. The Python was correct; `zsh` history expansion
was rewriting the `!` inside `'<!--page:'` in the double-quoted `-c` argument
before Python ever saw it.

**Resolution:** debug scripts written to a file and run with `PYTHONPATH=.`
rather than passed as inline `-c` strings.

**Presentation angle:** the tool reported a wrong fact about the system; the bug
was in the measurement, not the thing measured.

#### H11 — Progress output was invisible for the whole run
**Kind:** environmental · **Status:** resolved

`python -m evaluation run` piped to a file produced no output at all until the
process ended, because Python block-buffers stdout to a pipe. On a run of 20+
minutes this meant no way to tell progress from a hang.

**Resolution:** run with `python -u`, log to a file, and tail it.

#### H12 — Baseline comparison initially used the wrong report
**Kind:** analysis error (mine) · **Status:** corrected

The first before/after comparison selected the *oldest* report in
`eval_results/`, which was a leftover **3-question** run from previous work, not
the 34-question baseline. It produced a nonsense result (old prompt showing 0
refusals) that was caught and corrected before being reported as a finding.

**Fix:** the comparison script filters to reports with 34 samples.

**Presentation angle:** worth keeping — the check that caught it was noticing the
result was implausible, not the script failing.

#### H17 — A stated diagnosis was disproved by the next measurement
**Kind:** analysis error (mine) · **Status:** corrected

After the `top_k=5` runs, question 13 (`Is creatin monohidrate safe to take for
years?`) scored **0.00** context recall, and this was written up as *"the
misspelling defeats retrieval outright"* — a plausible reading that fitted the
question's design as a robustness probe.

The `top_k=10` run disproved it. The same question scores **1.00**. The correct
chunks were being retrieved at depth 5 all along; they were ranked below the
cutoff. The embedding model handled the misspelling; the *ranking* did not
surface it.

**Correction:** spelling-tolerant retrieval was demoted from a suggested next
step to low priority, because the symptom it was meant to address does not exist.

**Presentation angle:** the failure mode and the fix pointed in different
directions. A single-configuration measurement supported a wrong causal story,
and only varying a second parameter separated "not found" from "found but ranked
too low".

### Model and infrastructure

#### H13 — The model server dropped mid-run, twice
**Kind:** infrastructure · **Status:** recovered, not prevented

`openai/gpt-oss-20b` runs on a remote host over LM Studio's LM Link. It
disconnected during two separate runs:

- **Index build:** question generation failed for part of the corpus with
  `No models loaded`.
- **Evaluation run 2:** LM Link failed at judge job 26 with
  `peer_keepalive_timeout`, cascading to **110 of 136 judge calls failing**.

Ragas scores a failed call as NaN, which `_as_score()` converts to 0.0 — so the
run produced a complete, confident-looking report whose scores were meaningless.

**Handling:** the run was discarded. Its *answers* were generated before the drop
and were still valid, so the refusal comparison was taken from those while the
metrics were thrown away. A third run was made once the host returned.

**Presentation angle:** a distributed dependency turned a 25-minute measurement
into a silent data-quality problem. The report file
`eval_report_20260820_013754.json` still exists and should not be quoted.

#### H14 — The model failed to load twice
**Kind:** infrastructure · **Status:** resolved externally

`lms load openai/gpt-oss-20b` failed at 38% on two consecutive attempts. Because
both the pipeline **and the ragas judge** use this model, re-running on the
available fallback (`google/gemma-4-e2b`) would have changed the model *and* the
judge, making any before/after comparison meaningless. The re-run was held until
the model was available again.

### Findings that became fixes

#### H15 — The answering prompt refused questions it could answer
**Kind:** defect (pre-existing) · **Status:** fixed · **This is the headline finding**

The first evaluation surfaced it: **12 of 34 answers were a flat refusal**, and
only 3 of those were the questions written to be unanswerable. On the other 9 the
retrieval had already found the evidence — one had *perfect* context recall.

| # | recall | precision | question |
|---|---|---|---|
| 6 | **1.00** | 0.89 | Does glutamine keep athletes from getting sick? |
| 19 | 0.71 | **1.00** | Tart cherry or quercetin for recovery? |
| 21 | 0.67 | **1.00** | Since DHEA raises testosterone, what dose? |
| 22 | 0.71 | **1.00** | Can baking soda make me faster over 400 m? |
| 23 | 0.50 | 0.92 | 70 kg cyclist, three supplements compared |

**Root cause:** the prompt instructed the model to refuse whenever the sources
could not answer the question **"fully** and accurately". Five retrieved chunks
can almost never answer a multi-part or comparative question "fully", so the
model declined rather than answering the part it had. Each refusal scores 0 on
faithfulness and answer relevancy, dragging the aggregates below threshold.

**Fix** (`rag/answering.py`), grounding left strict:
- dropped **"fully"** from the refusal trigger;
- made grounded partial answers explicitly wanted — *"a grounded partial answer
  is what is wanted, not a refusal"*;
- reserved refusal for sources containing *"nothing bearing on the question at
  all"*.

**Why the old 3-question set could not have caught this:** all three were simple,
single-topic questions. The failure only appears on multi-part, comparative and
false-premise questions — which is precisely what the expanded set added.

#### H16 — Half the page citations bypassed verification
**Kind:** defect (introduced) · **Status:** fixed

Page citations are rewritten against the index after generation, so the page in
`[1, p. 19]` comes from retrieval metadata rather than from the model. The
matching regex accepted only ASCII brackets. `gpt-oss-20b` wrote **fullwidth**
brackets — `【4, p. 4】` — in **11 of 22 answers**, and every one of those passed
through untouched.

**Why it mattered:** an unrewritten citation is a page number the model chose,
displayed identically to one the index confirmed. That is the exact failure the
rewrite exists to prevent.

**Fix:** the pattern accepts `[` and `【`, and always emits the ASCII form. A
model-invented page is now replaced by the true one (`【4, p. 4】` → `[4, p. 7]`),
while a citation to a source that does not exist is deliberately left alone
rather than silently renumbered.

### Added 2026-08-20 (deck preparation)

#### H18 — A fourth evaluation run lost to the same host
**Kind:** infrastructure · **Status:** recovered, not prevented

A reranker evaluation was started against the local server with both models
confirmed loaded. It died at question 6 of 34: `openai/gpt-oss-20b` disappeared
from the host mid-run and `/chat/completions` began returning HTTP 400
`No models loaded`. A `GET /v1/models` immediately afterwards listed the
embedding models and `google/gemma-4-e2b`, with `gpt-oss-20b` simply gone.

**What behaved correctly:** `Reranker` caught the error, logged
`Skipping rerank (...)` and degraded to the dense order without losing a result
— exactly its designed fallback. `Answerer` has no such fallback, and raised.
That asymmetry is deliberate: a missing rerank costs ordering quality, whereas a
missing answer is not something to paper over.

**Running total:** four of seven evaluation runs have now been destroyed by this
host (`H13` twice, once during the reranker work, once here). The reranker
therefore remains **built, tested and unmeasured** — the claim that it improves
the metrics is still unverified, and is presented that way.

#### H19 — Embeddings and generation could not be separated
**Kind:** design constraint (pre-existing) · **Status:** fixed

Moving generation to a hosted gateway to escape `H18` was blocked by a single
field: `Settings.base_url` served both `/chat/completions` and `/embeddings`,
and `EvaluationEngine` resolved the judge's LLM *and* its embeddings from
`eval_endpoint()`. Pointing either at OpenRouter would have sent `/embeddings`
to a service that does not implement it.

The separation is required for a second, more important reason. The index's
1,144 vectors came from `text-embedding-embeddinggemma-300m`; querying it with
vectors from any other model is meaningless. So the embedder has to stay put
even when generation moves.

**Fix:** `embed_base_url` / `embed_api_key` (env `EMBED_BASE_URL`,
`EMBED_API_KEY`), both blank-inherits-`base_url`, plus `eval_embed_base_url` for
the judge. `RAGPipeline` builds a second `LLMClient` only when the endpoints
actually differ, so an unsplit setup still has one client and one rate limiter.
`LLM_RPM` was added at the same time, since pacing only matters against a
metered endpoint and could previously only be set from the UI.

`embed_base_url` is deliberately **not** in `VARIANT_FIELDS`: the same model at
a different hostname produces the same vectors, so the collection name is
unchanged and the existing index is reused. It *is* in `index_key`, because two
settings that reach different servers are not the same pipeline.

**Verified:** two new tests (`test_embeddings_can_be_served_from_a_different_host_than_generation`,
`test_a_split_embedding_endpoint_gets_its_own_client`) and one for the judge
(`test_the_judges_embeddings_follow_the_embedder_not_the_judge_endpoint`).
Suite: 54 pipeline + 12 evaluation = **66 passing**. Resolving a hybrid
configuration confirms generation on OpenRouter, embeddings on LM Studio, and
`collection_name` identical to the all-local default.

#### H20 — How much a model reasons is a property of the server, not the prompt
**Kind:** defect (exposed by the move) · **Status:** fixed

The first OpenRouter run looked healthy and was quietly running with two stages
disabled:

```
Skipping rerank (Empty reply (finish_reason='length', reasoning_tokens=651).)
Skipping query expansion (Empty reply (finish_reason='length', reasoning_tokens=273).)
```

Reasoning tokens come out of `max_tokens` — the README has said so since the
`gemma-4-e2b` experiment — but the budgets had been sized against a **local**
`gpt-oss-20b` that spends about **9** tokens reasoning on these prompts. The
same model id served by a hosted provider spent 651, then 2,260. `rerank_max_tokens`
was 512 and `query_expansion_max_tokens` 200, so every such call returned empty
and both stages fell back.

**Why it matters more than a truncated reply:** each stage's fallback is
correct in isolation — the reranker logs and degrades to dense order, the
expander logs and searches the query as typed. Neither is an error. So the run
produces a complete report for a pipeline **that is not the one being measured**,
and nothing in the report says so.

Measured on the pinned fp4 endpoint, same prompt:

| `reasoning.effort` | reasoning tokens |
|---|---|
| unset | 390 |
| medium | 238 |
| **low** | **15** |
| *local LM Studio, unset* | *~9* |

**Fix, in two parts:** budgets raised (`rerank_max_tokens` 512 → 2,048,
`query_expansion_max_tokens` 200 → 1,024 — a cap cannot shorten a reply that
already ended, so this is free locally), and `LLM_REASONING_EFFORT=low`, which
is not merely cheaper: at 15 tokens the hosted model reasons about as much as
the local one did, which is what keeps the two runs comparable at all.

**Presentation angle:** the same model id, the same quantization, the same
prompt — and a stage silently switched off, because the *server* decided to
think harder. Portability across providers is not free, and the failure is
invisible unless something is watching the log.

#### H21 — The judge was not pinned to the provider the pipeline was pinned to
**Kind:** defect (introduced) · **Status:** fixed

`Settings.extra_body()` reaches the pipeline through `LLMClient`, but the ragas
judge is built from `langchain_openai.ChatOpenAI`, which never saw it. So while
the pipeline was pinned to fp4 with fallbacks disabled, the judge was free to be
routed to any provider at any quantization — bf16 included — and to reason to a
different depth than the pipeline.

A judge routed differently between two runs is a different judge, and two runs
graded by different judges cannot be compared however carefully the pipeline was
held still. This is the same class of mistake as `H14`, arrived at from the
opposite direction: there the risk was noticed before the run, here it was built
in and had to be found.

**Fix:** `EvaluationEngine` now passes `extra_body` and `reasoning_effort` to
`ChatOpenAI`, so the judge is pinned exactly as the pipeline is.

---

## 3. Results

### 3.1 Golden set

3 questions → **34**. The original three are unchanged and remain first. The
additions are built to break specific things:

| Category | Questions |
|---|---|
| Out of scope — page cannot answer | 32 (carb loading), 33 (altitude), 34 (which brand) |
| Near-miss distractors | 16 arginine/citrulline, 17 beta-alanine/bicarbonate, 19 tart cherry/quercetin |
| Multi-hop across sections | 23 (three supplements + athlete tier), 24 (creatine + iron) |
| False premise | 21 (asks a DHEA dose; the page says DHEA does nothing) |
| Negation | 20 (which ingredients show *no* evidence) |
| Wrong-metric trap | 11 (a UL for creatine, which the page never states) |
| Terse / misspelled / acronym-only | 9 `beetroot juice dose timing`, 13 `creatin monohidrate`, 18 `HMB or BCAAs` |
| Synonym mismatch | 22 (baking soda → sodium bicarbonate) |

Schema was kept to exactly `{question, ground_truth}` because
`test_dataset_ships_questions_and_references_only` enforces it. Every reference
answer is traceable to the source page; the out-of-scope answers say the page
does not cover the topic *and* state what it does cover nearby, so their claims
stay attributable.

### 3.2 Extraction quality

| | value |
|---|---|
| Source PDF | 32 pages, 94,592 bytes |
| Headings recovered | 95 (from 0 structural markers in the PDF) |
| Chunks | 286 across 95 sections |
| Chunk size | min 111, median 490, max 600 chars; 125,499 total |
| Quality flags | 0 oversized, 0 tiny, 0 tables, 0 link-heavy, 0 no-prose |
| Index rows | 1,144 = 286 chunks + 858 questions |
| Page coverage | all 32 pages; 0 rows without a page |

### 3.3 Page citation accuracy

Verified independently by extracting the cited page from the PDF and confirming
the chunk text appears on it, across 5 questions and their top 3 hits each:

**15 of 15 correct, 0 wrong.**

24 chunks correctly span a page break and carry both pages (`pp. 4-5`).

### 3.4 Evaluation — before and after the prompt fix

Same 34 questions, same index, same model and judge (`openai/gpt-oss-20b`), same
threshold (0.80). Only the answering prompt changed.

| metric | before | after | delta |
|---|---|---|---|
| context recall | 0.6134 | 0.6283 | +0.015 |
| context precision | 0.7470 | 0.7931 | +0.046 |
| **faithfulness** | 0.5923 | **0.7696** | **+0.177** |
| **answer relevancy** | 0.5820 | **0.7361** | **+0.154** |

| | before | after |
|---|---|---|
| refusals (of 34) | 12 | **5** |
| — over-refusals | 9 | **2** |
| — correct refusals (of 3) | 3 | **3** |
| failing samples | 28 | 27 |
| zero scores (of 136) | 27 | **10** |

Per-sample passes at threshold, out of 34:

| metric | before | after |
|---|---|---|
| context recall | 11 | 12 |
| context precision | 22 | 27 |
| faithfulness | 18 | 26 |
| answer relevancy | 14 | 19 |

**The control that makes this credible:** context recall barely moved (+0.015).
A prompt cannot change what retrieval fetched, so a large recall movement would
have indicated something else was varying. The two *answering* metrics moved by
an order of magnitude more, which is exactly the predicted shape.

**Excluding the 3 deliberately-unanswerable questions** (which score faithfulness
0.00 by construction — "the page does not cover this" is a claim no retrieved
chunk can support):

| metric | 31 answerable questions | verdict |
|---|---|---|
| context precision | 0.8224 | **PASS** |
| faithfulness | 0.8441 | **PASS** |
| answer relevancy | 0.7827 | fail |
| context recall | 0.6600 | fail |

### 3.5 Cost of a run

| | |
|---|---|
| Collection | 34 questions × (1 expansion + 1 search + 1 answer) |
| Scoring | 136 judge calls (34 samples × 4 metrics), `eval_max_workers: 1` |
| Wall clock | ~22m43s scoring + ~10 min collection |

---

### 3.6 Retrieval depth — `top_k` 5 vs 10

Same index, same prompt, same model and judge. Only retrieval depth changed, so
this isolates the one variable. Run: `eval_report_20260820_033634.json`.

| metric | k=5 | k=10 | delta |
|---|---|---|---|
| **context recall** | 0.628 | **0.781** | **+0.152** |
| context precision | 0.793 | 0.714 | −0.079 |
| faithfulness | 0.770 | 0.786 | +0.016 |
| answer relevancy | 0.736 | 0.688 | −0.048 |

Excluding the 3 deliberately-unanswerable questions:

| metric | k=5 | k=10 | k=10 verdict |
|---|---|---|---|
| **context recall** | 0.660 | **0.822** | **PASS** |
| context precision | 0.822 | 0.739 | fail |
| **faithfulness** | 0.844 | **0.862** | **PASS** |
| answer relevancy | 0.783 | 0.742 | fail |

Samples passing at threshold, out of 34:

| metric | k=5 | k=10 |
|---|---|---|
| context recall | 12 | **23** |
| context precision | 27 | 19 |
| faithfulness | 26 | 23 |
| answer relevancy | 19 | 18 |

Failing samples 27 → **25**. Refusals unchanged at 5 (2 over-refusals), which is
the expected control: depth does not change the prompt's willingness to answer.

**This is a genuine trade-off, not a free win.** Recall rises sharply and
faithfulness edges up — more evidence reaches the answerer, so more of its claims
are supported. Precision falls by almost as much as recall rises, because ten
chunks per question means more of them are off-topic. Answer relevancy also
slips, consistent with a longer, more diluted answer.

**The questions that moved are exactly the edge cases the expanded set added**,
which confirms the "right neighbourhood, not enough of it" diagnosis:

| # | k=5 → k=10 | kind |
|---|---|---|
| 13 | **0.00 → 1.00** | misspelling (`creatin monohidrate`) |
| 30 | 0.29 → 0.86 | evidence quality, spread across the introduction |
| 23 | 0.50 → 1.00 | multi-part (three supplements + athlete tier) |
| 22 | 0.57 → 1.00 | synonym mismatch (baking soda) |
| 19 | 0.57 → 1.00 | near-miss distractor (tart cherry / quercetin) |
| 18 | 0.60 → 1.00 | acronym comparative (HMB / BCAAs) |

Every multi-hop and comparative question reached perfect recall. The misspelling
case went from total failure to perfect — at depth 5 the correct chunks were
being found but ranked below the cutoff, not missed.

Two questions lost ground: #31 (0.40 → 0.20) and #12 (1.00 → 0.83).

**Caveat:** one judge call of 136 failed with an `OutputParserException`, scoring
one metric 0. Zero scores went 10 → 11 between the two runs. The same class of
failure occurred once in the baseline run; it is judge flakiness, not pipeline
behaviour.

**Reading:** for a pipeline whose job is grounded, citable answers, recall and
faithfulness matter more than precision — a chunk that is retrieved but unused
costs little, whereas evidence that is never retrieved cannot be cited at all.
On that reading `top_k=10` is the better setting, and it is the only
configuration measured so far where any metric passes on the answerable
questions. Neither configuration passes all four.

#### Outcome — the default was changed

`top_k` now defaults to **10**, set in `rag/config.py` with the measurement
recorded in the comment so the number does not read as taste. `Retriever`'s own
constructor default moved with it so the stage and `Settings` cannot disagree.

What that default buys and costs, over all 34 questions:

| | gained | cost |
|---|---|---|
| context recall | +0.152 (0.628 → 0.781) | |
| faithfulness | +0.016 (0.770 → 0.786) | |
| context precision | | −0.079 (0.793 → 0.714) |
| answer relevancy | | −0.048 (0.736 → 0.688) |

Samples passing at threshold: recall 12 → 23, precision 27 → 19, faithfulness
26 → 23, relevancy 19 → 18. Failing samples 27 → 25.

**No rebuild was required.** `top_k` is a query-time setting pushed onto the live
retriever by `RAGPipeline.apply()`; it is not part of `collection_name`, so the
index (1,144 rows) is untouched. The Streamlit slider reads `defaults.top_k` and
follows automatically, and `--top-k` still overrides per run.

The README's `top_k` table was replaced at the same time — it had been measured
on the original 3 questions (0.730 → 0.944 recall) and now carries the
34-question figures across all four metrics.

### 3.7 Reranking — the first clean measurement

Run: `eval_report_20260820_072455.json`, on OpenRouter with the provider pinned
to fp4 and `reasoning.effort=low` (see `H20`). Judge pinned identically (`H21`).
Compared against `eval_report_20260820_033634.json` — same index, same prompt,
same `top_k`, same model id and quantization; reranking on, and the host
changed. Over the 31 answerable questions:

| metric | dense only | with reranking | delta |
|---|---|---|---|
| **context precision** | 0.739 | **0.819 PASS** | **+0.080** |
| answer relevancy | 0.742 | 0.783 | +0.040 |
| context recall | 0.822 PASS | 0.817 PASS | −0.006 |
| faithfulness | 0.862 PASS | 0.838 PASS | −0.024 |

Over all 34: recall 0.781 → 0.799, precision 0.714 → 0.754, faithfulness
0.786 → 0.764, relevancy 0.688 → 0.725. Samples passing at threshold: precision
19 → **23**, relevancy 18 → **21**, faithfulness 23 → 24, recall unchanged at
23. Failing samples 25 → **21**. Zero scores 13 of 136, against 27 in the worst
local run — this is the cleanest run made so far.

**Three of four metrics now pass on the answerable questions**, where no
previous configuration passed more than two.

**The control ran, and it corrected the reading above.** A second run at
`RAG_ENABLE_RERANK=false` on the same pinned endpoint
(`eval_report_20260820_075840.json`) isolates reranking from the host move.
Over the 31 answerable questions:

| metric | local dense | hosted dense *(control)* | hosted + rerank | reranking alone |
|---|---|---|---|---|
| **context precision** | 0.739 | 0.735 | **0.819** | **+0.084** |
| answer relevancy | 0.742 | 0.768 | 0.783 | +0.014 |
| context recall | 0.822 | 0.851 | 0.816 | −0.035 |
| faithfulness | 0.862 | 0.870 | 0.838 | −0.033 |

Two things follow, and the second is a correction.

**The host was not neutral.** Moving generation to the pinned fp4 endpoint
raised recall by 0.029 and relevancy by 0.026 on its own, with no code change.
Precision moved −0.004, which is the useful part: the metric the reranker claim
rests on is the one the host barely touched.

**Recall is not flat, and the earlier framing was wrong.** Against the local
baseline reranking looked like −0.006 on recall, and that was written up here as
the control that proved the mechanism. Isolated properly it is **−0.035**, and
faithfulness gives up a similar amount. The reason is mechanical and should have
been predicted: reranking decides *which ten of the twenty* reach the answer, so
it can drop a chunk dense retrieval had kept. It does not only reorder within
what would have been returned anyway.

The honest statement is a trade, not a free win: **about three points of recall
and groundedness bought about eight points of precision**, and the trade is
worth taking because precision was the failing metric and the other two had
margin above threshold. Samples failing fell 26 → 21.

**Presentation angle:** the confound was real, the control was worth the
40 minutes, and it turned a claim that was too good into one that is true. This
is the third time in this log that a second measurement has corrected a
conclusion drawn from a single configuration (see `H12`, `H17`).

## 4. Still open

At the shipped configuration (`top_k=10`, fixed prompt), over the 31 answerable
questions: context recall **0.822 PASS**, faithfulness **0.862 PASS**, context
precision 0.739, answer relevancy 0.742. Over all 34: 0.781 / 0.786 / 0.714 /
0.688. Two of four metrics pass; no configuration measured passes all four.

**Precision and answer relevancy are now the weak pair**, and they are the side
of the trade `top_k=10` was bought with. Both sit close to threshold rather than
far below it.

**Where recall still fails**, and what depth did to each. The `top_k=5` column is
what the earlier diagnosis was built on; the `top_k=10` column is what actually
happened:

| # | k=5 | k=10 | reading |
|---|---|---|---|
| 13 | 0.00 | **1.00** | not a spelling problem — a ranking cutoff (see `H17`) |
| 30 | 0.29 | **0.86** | evidence-quality claims spread across the introduction |
| 20 | 0.12 | 0.25 | negation: retrieves the topic, not the absence of evidence |
| 11 | 0.33 | 0.33 | asks for a value the page never states |
| 31 | 0.40 | 0.20 | **regressed** with depth |
| 12 | 1.00 | 0.83 | **regressed** with depth |

The cases depth barely helped are the genuinely hard ones: **negation** (#20,
0.12 → 0.25) and **asking for a value that does not exist** (#11, unchanged at
0.33). Neither is a depth problem — retrieving more chunks cannot surface an
absence. These would need either query rewriting or an answering step that
reasons about what is missing.

**Remaining, in order:**
1. Measure a `top_k` between 5 and 10. The middle of the range is unexplored, and
   it is where a configuration passing three metrics is most likely to sit.
2. Revisit the 2 remaining over-refusals (#11, #31).
3. Investigate the two depth regressions (#31, #12) — small, but they are the
   only questions the change made worse.
4. Negation and absent-value queries (#20, #11) — not addressable by retrieval
   tuning.
5. Spelling-tolerant retrieval — **deprioritised**, see `H17`.

**Housekeeping:** `eval_results/eval_report_20260820_013754.json` is the aborted
run (valid answers, meaningless scores). Delete it or it will be mistaken for a
real result.

---

## 5. Reproducing the figures

```bash
.venv/bin/python -m rag.cli chunks                    # chunk counts and flags
.venv/bin/python -m rag.cli query "<question>" --answer
.venv/bin/python -u -m evaluation run                 # full evaluation (~30 min)
.venv/bin/python -u -m evaluation run --top-k 10      # at a different depth
.venv/bin/python tests/test_pipeline.py               # 45 tests
.venv/bin/python tests/test_evaluation.py             # 11 tests
.venv/bin/python tools/build_source_pdf.py            # rebuild the source PDF
```

Reports used in this document:

| file | run |
|---|---|
| `eval_results/eval_report_20260820_010736.json` | baseline, old prompt |
| `eval_results/eval_report_20260820_013754.json` | **aborted** — do not quote scores |
| `eval_results/eval_report_20260820_020829.json` | after the prompt fix, `top_k=5` |
| `eval_results/eval_report_20260820_033634.json` | after the prompt fix, `top_k=10` |
