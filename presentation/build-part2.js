"use strict";
/** Slides 14-26: the technical work, the measurements, and what went wrong. */

const K = require("./lib/kit");
const { measure } = require("./lib/metrics");
const { C, F, W, M } = K;

/**
 * Left-hand "the constraint / what we did / what it cost" narrative column.
 * Each beat is sized from its own text, so adding a sentence pushes the rest
 * down rather than printing on top of it.
 */
function beats(slide, x, y, w, items, opts = {}) {
  let cy = y;
  items.forEach((it) => {
    slide.addText(it[0].toUpperCase(), {
      x, y: cy, w, h: 0.22, margin: 0,
      fontFace: F.body, fontSize: 8.5, bold: true, charSpacing: 1.1,
      color: it[2] || C.orange,
    });
    const box = {
      fontFace: F.body, fontSize: opts.size || 11, w, margin: 0,
      lineSpacing: opts.lineSpacing || 14.5,
    };
    const h = measure(it[1], box).height;
    slide.addText(it[1], Object.assign({}, box, {
      x, y: cy + 0.23, h,
      color: opts.dark ? C.muteDark : "39485C", valign: "top",
    }));
    cy += 0.23 + h + (opts.gap === undefined ? 0.18 : opts.gap);
  });
  return cy;
}

module.exports = function part2(pres) {
  let s, y;

  // ======================================================================= //
  // 14 — DIVIDER 05
  // ======================================================================= //
  s = pres.addSlide();
  K.divider(s, "05", "Section five", "The technical work",
    "Four layers, each with the defect that taught us how to build it. Every number that follows was measured, not estimated.");

  // ======================================================================= //
  // 15 — INGESTION: STRUCTURE
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 1 · Ingestion", "A PDF has no headings. The whole pipeline depends on them.");

  const beatsEnd = beats(s, M, y + 0.04, 5.7, [
    ["The constraint",
     "Chunks are cut at headings and stamped with their heading path — “Creatine > Efficacy”. Those breadcrumbs are load-bearing: they stop a chunk mixing two ingredients and let every chunk state its own subject. A PDF contains none of it — only glyphs at coordinates.", C.orange, 1.06],
    ["What we did",
     "PdfReader recovers structure from the one signal that survives into the file. Distinct font sizes above the body size are ranked and mapped onto heading levels 1..N. Paragraphs are rejoined by noticing which lines stop short of the right margin. Nothing is hard-coded to this document.", C.orange, 1.06],
    ["The defect it took to get right",
     "Our first running-head filter dropped short lines that repeated across most pages. In this document “Efficacy” and “Safety” head a subsection under each of ~21 ingredients — so they repeat, and they were deleted. 36 headings recovered where the source has 95. A running head is now defined by position as well as repetition: it must repeat and sit in the top or bottom 8% of the page.", C.red, 1.4],
  ]);

  K.card(s, { x: 6.66, y: y + 0.04, w: W - M - 6.66, h: 1.72, fill: C.tint });
  s.addText("Headings recovered", {
    x: 6.92, y: y + 0.2, w: 3.0, h: 0.26, margin: 0,
    fontFace: F.body, fontSize: 10, bold: true, charSpacing: 0.8, color: C.mute,
  });
  K.stat(s, { x: 6.92, y: y + 0.52, w: 1.5, value: "36", label: "first attempt", size: 42, color: C.red, vh: 0.7, labelSize: 10 });
  s.addText("→", {
    x: 8.42, y: y + 0.52, w: 0.6, h: 0.7, margin: 0, align: "center", valign: "middle",
    fontFace: F.body, fontSize: 22, color: C.mute,
  });
  K.stat(s, { x: 9.02, y: y + 0.52, w: 1.6, value: "95", label: "after the fix — matching the source structure", size: 42, color: C.green, vh: 0.7, labelSize: 10 });

  s.addText("Extraction quality — the notebook this replaced, and the pipeline now", {
    x: 6.66, y: y + 1.92, w: W - M - 6.66, h: 0.26, margin: 0,
    fontFace: F.body, fontSize: 10, bold: true, charSpacing: 0.8, color: C.mute,
  });

  s.addChart(pres.ChartType.bar, [
    { name: "Notebook", labels: ["Chunks", "Under 100 chars", "Flagged suspect"], values: [463, 35, 43] },
    { name: "Pipeline", labels: ["Chunks", "Under 100 chars", "Flagged suspect"], values: [286, 0, 1] },
  ], K.chartFrame({
    x: 6.72, y: y + 2.2, w: W - M - 6.84, h: 1.42,
    barDir: "bar",
    chartColors: [C.rule, C.ink],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.mute,
    showLegend: true, legendPos: "b", legendFontFace: F.body, legendFontSize: 9, legendColor: C.mute,
    valAxisHidden: true, valGridLine: { style: "none" }, valAxisMaxVal: 560,
    barGapWidthPct: 40, catAxisLabelFontSize: 9.5,
  }));

  s.addText(
    "286 chunks across 95 sections. 0 oversized, 0 tiny, 0 link-only, 0 without prose — and 37% fewer embeddings to pay for than the notebook produced.",
    {
      x: M, y: beatsEnd + 0.08, w: 6.0, h: 0.5, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  // ======================================================================= //
  // 16 — PROVENANCE
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 1 · Provenance", "How a page number survives six stages of rewriting");

  const flow = [
    ["PdfReader", "prefixes each page's text with an HTML comment marker"],
    ["MarkdownCleaner", "rewrites nearly every character — and matches none of its patterns against an HTML comment"],
    ["MarkdownChunker", "reads the marker, records the page(s) on the chunk, strips it before indexing"],
    ["VectorIndex", "stores it in Chroma metadata as a scalar \"4,5\" — Chroma holds no sequences"],
    ["Answerer", "labels every source with its page before the model ever sees it"],
  ];

  flow.forEach((f, i) => {
    const fy = y + 0.06 + i * 0.63;
    K.chip(s, i + 1, M, fy + 0.06, { diam: 0.32, size: 12 });
    s.addText(f[0], {
      x: M + 0.46, y: fy, w: 1.86, h: 0.28, margin: 0,
      fontFace: F.mono, fontSize: 10, bold: true, color: C.ink,
    });
    s.addText(f[1], {
      x: M + 2.36, y: fy, w: 3.86, h: 0.5, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 13.5,
    });
  });

  K.mono(s, "<!--page:19-->\n# Creatine\n\nCreatine is an amino acid ...", {
    x: 6.98, y: y + 0.06, w: 3.0, h: 0.94, size: 9.5, lineSpacing: 13,
  });
  s.addText("The marker is an HTML comment on purpose — it is the one shape the cleaner does not touch.", {
    x: 10.14, y: y + 0.1, w: W - M - 10.14, h: 0.9, margin: 0,
    fontFace: F.body, fontSize: 10, italic: true, color: C.mute, valign: "top", lineSpacing: 13.5,
  });

  const prov = [["32", "of 32 pages\ncovered"], ["0", "indexed rows\nwithout a page"], ["24", "chunks correctly\nspanning a break"]];
  prov.forEach((p, i) => {
    const px = 6.98 + i * 1.86;
    K.card(s, { x: px, y: y + 1.16, w: 1.72, h: 1.16, fill: C.tint, flat: true });
    s.addText(p[0], {
      x: px, y: y + 1.28, w: 1.72, h: 0.5, margin: 0, align: "center", valign: "middle",
      fontFace: F.head, fontSize: 28, bold: true, color: C.ink,
    });
    s.addText(p[1], {
      x: px, y: y + 1.76, w: 1.72, h: 0.44, margin: 0, align: "center",
      fontFace: F.body, fontSize: 9.5, color: C.mute, lineSpacing: 12,
    });
  });

  K.card(s, { x: M, y: y + 3.34, w: W - M * 2, h: 0.94, fill: "FDF1EC", line: "F3D8CB" });
  K.pill(s, "THE SILENT FAILURE", { x: M + 0.26, y: y + 3.5, fill: C.red });
  s.addText(
    [
      { text: "The reader checked its cache before validating that the source was a PDF. ", options: { bold: true, color: C.ink } },
      { text: "Our .env still pointed at the old HTML file, whose cache entry existed — so it returned HTML-derived markdown with no page markers at all. All 288 chunks had zero pages and nothing raised. About 20 minutes lost. The fix validates the extension first, and a regression test plants a stale cache entry and asserts the reader still refuses. The most expensive failures are the ones that do not throw.", options: { color: "5A4038" } },
    ],
    {
      x: M + 2.02, y: y + 3.46, w: W - M * 2 - 2.3, h: 0.72, margin: 0,
      fontFace: F.body, fontSize: 10, valign: "top", lineSpacing: 13.5,
    }
  );

  // ======================================================================= //
  // 17 — RETRIEVAL PATH
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 2 · Retrieval", "What happens between a question and the evidence");

  const steps = [
    ["Expand", "The model is asked for a few other phrasings — domain terms and scientific synonyms — so the index is searched for passages worded unlike the question."],
    ["Search", "Each phrasing is embedded with the query instruction template and run against the collection: 286 chunk rows and 858 hypothetical-question rows."],
    ["Merge", "Hits are pooled and agreement is counted one vote per phrasing — never per matching row, or a chunk found through three of its own questions would look like three confirmations."],
    ["Collapse", "One result per parent chunk, so a single passage cannot fill every slot through the questions generated for it."],
    ["Rerank", "The pool of 20 goes into one prompt and comes back as an order."],
    ["Cut", "Only now is the list truncated to top_k = 10 and handed to the answerer."],
  ];

  const sw = (W - M * 2 - 0.5) / 3;
  steps.forEach((st, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M + col * (sw + 0.25);
    const sy = y + 0.04 + row * 1.62;
    K.card(s, { x, y: sy, w: sw, h: 1.44 });
    K.chip(s, i + 1, x + 0.24, sy + 0.22, { diam: 0.32, size: 12 });
    s.addText(st[0], {
      x: x + 0.66, y: sy + 0.24, w: sw - 0.9, h: 0.28, margin: 0,
      fontFace: F.head, fontSize: 14, bold: true, color: C.ink, valign: "middle",
    });
    s.addText(st[1], {
      x: x + 0.24, y: sy + 0.62, w: sw - 0.48, h: 0.7, margin: 0,
      fontFace: F.body, fontSize: 10, color: "46566B", valign: "top", lineSpacing: 13,
    });
  });

  s.addText(
    [
      { text: "The number beside a result never overstates the match. ", options: { bold: true, color: C.ink } },
      { text: "Agreement lifts a chunk up the ranking through Retrieved.score, but Retrieved.similarity stays exactly what the embedder returned — so a boosted result says how many phrasings agreed and what it was given, rather than quietly inflating its own confidence.", options: { color: "46566B" } },
    ],
    {
      x: M, y: y + 3.34, w: W - M * 2, h: 0.62, margin: 0,
      fontFace: F.body, fontSize: 11, valign: "top", lineSpacing: 14.5,
    }
  );

  // ======================================================================= //
  // 18 — RERANKING
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 2 · Reranking", "We measured where the evidence sits, before building anything");

  y = K.lede(s, y,
    "The embedder scores question and passage separately — neither vector ever sees the other. A reranker reads them "
    + "together, which is why it can tell a passage that shares vocabulary from one that answers.");

  s.addChart(pres.ChartType.bar, [
    { name: "In dense top-5", labels: ["Where the evidence lands"], values: [45] },
    { name: "At dense ranks 6-20", labels: ["Where the evidence lands"], values: [41] },
    { name: "Not in top-20", labels: ["Where the evidence lands"], values: [14] },
  ], K.chartFrame({
    x: M, y: y + 0.02, w: W - M * 2, h: 1.16,
    barDir: "bar", barGrouping: "stacked",
    chartColors: [C.green, C.orange, C.red],
    showValue: true, dataLabelPosition: "ctr", dataLabelColor: "FFFFFF", dataLabelFontSize: 12,
    showLegend: true, legendPos: "b", legendFontFace: F.body, legendFontSize: 10, legendColor: C.mute,
    valAxisHidden: true, valGridLine: { style: "none" }, catAxisHidden: true,
    barGapWidthPct: 30,
  }));

  s.addText(
    "Method: query the index with each golden reference answer — the passages nearest an ideal answer are what retrieval ought to surface — then check where they land in the real ranking.",
    {
      x: M, y: y + 1.24, w: W - M * 2, h: 0.4, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  const rr = [
    ["41% is a ranking problem, not a recall problem", "Two-fifths of the evidence is retrieved and then ranked too low. That is a reranker's job exactly. Corroborated independently: recall jumped 0.628 → 0.781 going from depth 5 to 10.", C.orange],
    ["Listwise, not pointwise", "Every candidate goes into one prompt and the model returns an order — one generation call per search, the same budget query expansion already spends. No new dependency.", C.orange],
    ["Rerank the pool, then cut", "Ranking only what dense already preferred would defeat the point. It reorders and never filters: candidates the model omits keep their dense order behind the ones it chose.", C.orange],
  ];
  const rw = (W - M * 2 - 0.42) / 3;
  rr.forEach((r, i) => {
    const x = M + i * (rw + 0.21);
    K.card(s, { x, y: y + 1.66, w: rw, h: 1.46 });
    s.addText(r[0], {
      x: x + 0.24, y: y + 1.8, w: rw - 0.48, h: 0.44, margin: 0,
      fontFace: F.head, fontSize: 12.5, bold: true, color: C.ink, valign: "top", lineSpacing: 15,
    });
    s.addText(r[1], {
      x: x + 0.24, y: y + 2.26, w: rw - 0.48, h: 0.78, margin: 0,
      fontFace: F.body, fontSize: 10, color: "46566B", valign: "top", lineSpacing: 13,
    });
  });

  K.card(s, { x: M, y: y + 3.2, w: W - M * 2, h: 0.86, fill: "EDF6F2", line: "C6E4D8" });
  K.pill(s, "MEASURED", { x: M + 0.26, y: y + 3.34, fill: C.green });
  s.addText(
    [
      { text: "Context precision 0.739 → 0.819", options: { bold: true, color: C.ink } },
      { text: " over the answerable questions — the metric reranking exists to move, and the one that was failing. Answer relevancy rises 0.040 with it, because a cleaner context makes a less diluted answer. ", options: { color: "38504A" } },
      { text: "Recall is flat at −0.006", options: { bold: true, color: C.ink } },
      { text: ", which is the control: a reranker reorders what dense retrieval already found, so it cannot add evidence. That is exactly the shape the mechanism predicts.", options: { color: "38504A" } },
    ],
    {
      x: M + 1.62, y: y + 3.3, w: W - M * 2 - 1.9, h: 0.68, margin: 0,
      fontFace: F.body, fontSize: 10, valign: "top", lineSpacing: 13.5,
    }
  );

  // ======================================================================= //
  // 19 — GROUNDING & CITATIONS
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 3 · Grounding", "Asking for a citation is not the same as having one");

  beats(s, M, y + 0.04, 5.8, [
    ["The principle",
     "The model chooses which source supports a claim. The page that source came from is not its to invent. So every citation it writes is rewritten against the index afterwards — the page of source n is something the answerer already knows, and looking it up beats trusting the model to copy it.", C.orange, 1.06],
    ["And where it stops",
     "A citation pointing at a source that does not exist is left exactly as it is. Silently renumbering it would hide the model inventing a source — which is the one thing this must surface.", C.orange, 0.72],
  ]);

  K.mono(s,
    "prompt   →  Cite every claim as [1, p. 12]\n\n" +
    "model    →  ... 5 g U+3010 4, p. 4 U+3011\n" +
    "                    ^^^^^^^^^^^^^^^^^^^^\n" +
    "                    fullwidth CJK brackets\n\n" +
    "rewrite  →  ... 5 g [4, p. 7]\n" +
    "                     ^^^^^\n" +
    "           page from Retrieved.pages,\n" +
    "           never from the model",
    { x: M, y: y + 1.94, w: 5.8, h: 2.16, size: 9.5, lineSpacing: 13.5 }
  );

  K.card(s, { x: 6.86, y: y + 0.04, w: W - M - 6.86, h: 2.32, fill: "FDF1EC", line: "F3D8CB" });
  K.pill(s, "THE DEFECT", { x: 7.12, y: y + 0.2, fill: C.red });
  s.addText("Half the citations bypassed verification", {
    x: 7.12, y: y + 0.5, w: 5.4, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });
  s.addText(
    "The matching pattern accepted only ASCII brackets. gpt-oss-20b reaches instead for the fullwidth CJK variants, U+3010 and U+3011 — in 11 of 22 answers in one run — and every one of those passed through untouched.\n\n" +
    "An unrewritten citation is a page the model chose, displayed identically to one the index confirmed. That is precisely the failure the rewrite exists to prevent. The pattern now accepts both and always emits the ASCII form.",
    {
      x: 7.12, y: y + 0.84, w: 5.4, h: 1.4, margin: 0,
      fontFace: F.body, fontSize: 10, color: "5A4038", valign: "top", lineSpacing: 13.5,
    }
  );

  K.card(s, { x: 6.86, y: y + 2.5, w: W - M - 6.86, h: 1.38, fill: C.tint });
  s.addText("Verified by hand", {
    x: 7.12, y: y + 2.66, w: 3.0, h: 0.28, margin: 0,
    fontFace: F.body, fontSize: 10, bold: true, charSpacing: 0.8, color: C.mute,
  });
  K.stat(s, {
    x: 7.12, y: y + 2.96, w: 2.2, value: "15/15",
    label: "citations correct, 0 wrong — across 5 questions and their top 3 hits each",
    size: 30, color: C.green, vh: 0.5, labelSize: 9.5,
  });
  s.addText("Method: pull the cited page out of the PDF and confirm the chunk text is on it.", {
    x: 9.5, y: y + 2.98, w: 3.0, h: 0.72, margin: 0,
    fontFace: F.body, fontSize: 9.5, italic: true, color: C.mute, valign: "top", lineSpacing: 13,
  });

  // ======================================================================= //
  // 20 — SAFETY
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Layer 4 · Clinical safety", "Refusing too much is a safety failure too");

  K.card(s, { x: M, y: y + 0.04, w: 6.1, h: 2.16, fill: "FDF1EC", line: "F3D8CB" });
  K.pill(s, "THE HEADLINE FINDING", { x: M + 0.26, y: y + 0.2, fill: C.red });
  s.addText("The prompt refused questions it could answer", {
    x: M + 0.26, y: y + 0.5, w: 5.6, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });
  s.addText(
    "Our first evaluation returned 12 refusals out of 34 — and only 3 of those were the questions written to be unanswerable. On the other 9 retrieval had already found the evidence; one had perfect context recall.\n\n" +
    "Root cause: the prompt refused whenever the sources could not answer the question “fully”. Five chunks can almost never answer a multi-part or comparative question fully, so the model declined instead of answering the part it had.",
    {
      x: M + 0.26, y: y + 0.84, w: 5.6, h: 1.26, margin: 0,
      fontFace: F.body, fontSize: 10, color: "5A4038", valign: "top", lineSpacing: 13.5,
    }
  );

  K.card(s, { x: 7.02, y: y + 0.04, w: W - M - 7.02, h: 2.16, fill: C.tint });
  s.addText("The fix — grounding left strict", {
    x: 7.28, y: y + 0.2, w: 5.2, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });
  s.addText(
    [
      { text: "· dropped “fully” from the refusal trigger\n", options: { color: "39485C" } },
      { text: "· made grounded partial answers explicitly wanted — a partial answer is what is required, not a refusal\n", options: { color: "39485C" } },
      { text: "· reserved refusal for sources containing nothing bearing on the question at all\n\n", options: { color: "39485C" } },
      { text: "Refusals 12 → 5. Over-refusals 9 → 2. ", options: { bold: true, color: C.ink } },
      { text: "The three deliberately unanswerable questions are still refused, all three.", options: { color: "39485C" } },
    ],
    {
      x: 7.28, y: y + 0.56, w: 5.2, h: 1.56, margin: 0,
      fontFace: F.body, fontSize: 10, valign: "top", lineSpacing: 13.8,
    }
  );

  s.addText("At the shipped configuration, all five refusals are on questions the corpus cannot properly answer", {
    x: M, y: y + 2.34, w: W - M * 2, h: 0.28, margin: 0,
    fontFace: F.body, fontSize: 11, bold: true, color: C.ink,
  });

  const refusals = [
    ["#32", "Carbohydrate loading protocol", "Out of scope by design"],
    ["#33", "How altitude training works", "Out of scope by design"],
    ["#34", "Which brand should I buy", "Out of scope by design"],
    ["#11", "Upper intake level for creatine", "A value the page never states"],
    ["#21", "What DHEA dose for male athletes", "False premise — the page says DHEA does not work"],
  ];
  const fw = (W - M * 2 - 0.6) / 5;
  refusals.forEach((r, i) => {
    const x = M + i * (fw + 0.15);
    K.card(s, { x, y: y + 2.66, w: fw, h: 1.08, fill: C.tint, flat: true });
    s.addText(r[0], {
      x: x + 0.16, y: y + 2.76, w: fw - 0.32, h: 0.24, margin: 0,
      fontFace: F.mono, fontSize: 10, bold: true, color: C.orange,
    });
    s.addText(r[1], {
      x: x + 0.16, y: y + 2.98, w: fw - 0.32, h: 0.4, margin: 0,
      fontFace: F.body, fontSize: 9.5, bold: true, color: C.ink, valign: "top", lineSpacing: 12,
    });
    s.addText(r[2], {
      x: x + 0.16, y: y + 3.36, w: fw - 0.32, h: 0.32, margin: 0,
      fontFace: F.body, fontSize: 8.5, color: C.mute, valign: "top", lineSpacing: 11,
    });
  });

  s.addText(
    "The metric scores the last two as failures — ragas has no way to reward a correct decline. As safety behaviour they are right, and we would rather the system refuse a dose that does not exist.",
    {
      x: M, y: y + 3.84, w: W - M * 2, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  // ======================================================================= //
  // 21 — EVALUATION METHOD
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Evaluation", "Judging retrieval by eye stops scaling around the third question");

  const metrics = [
    ["Context recall", "Retriever", "Did it find the evidence the reference answer needs?"],
    ["Context precision", "Retriever", "Are the chunks it returned actually about the question?"],
    ["Faithfulness", "Answerer", "Is the answer grounded in those chunks?"],
    ["Answer relevancy", "Answerer", "Does the answer address the question that was asked?"],
  ];
  metrics.forEach((m, i) => {
    const my = y + 0.06 + i * 0.62;
    K.card(s, { x: M, y: my, w: 6.0, h: 0.54, fill: i < 2 ? C.tint : C.paper, line: C.tintDeep, flat: true });
    s.addText(m[0], {
      x: M + 0.18, y: my, w: 1.9, h: 0.54, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 11, bold: true, color: C.ink,
    });
    s.addText(m[1], {
      x: M + 2.06, y: my, w: 1.0, h: 0.54, margin: 0, valign: "middle",
      fontFace: F.mono, fontSize: 9, color: i < 2 ? C.orange : C.green,
    });
    s.addText(m[2], {
      x: M + 3.06, y: my, w: 2.8, h: 0.54, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 9.5, color: "46566B", lineSpacing: 12,
    });
  });

  s.addText(
    "Two grade retrieval and two grade generation — so a failing metric names the stage to look at, rather than saying “the RAG is bad”.",
    {
      x: M, y: y + 2.62, w: 6.0, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  K.card(s, { x: 7.0, y: y + 0.06, w: W - M - 7.0, h: 3.62, fill: C.ink, line: C.ink });
  s.addText("A golden set built to break things", {
    x: 7.26, y: y + 0.24, w: 5.2, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 15, bold: true, color: C.paper,
  });
  s.addText("3 questions → 34. Most of them are there to defeat something in particular.", {
    x: 7.26, y: y + 0.56, w: 5.2, h: 0.26, margin: 0,
    fontFace: F.body, fontSize: 10, italic: true, color: C.mute,
  });

  const kinds = [
    ["Out of scope ×3", "the page cannot answer them at all"],
    ["Near-miss distractors ×3", "arginine/citrulline, beta-alanine/bicarbonate, tart cherry/quercetin"],
    ["Multi-hop ×2", "the answer lives in two ingredient sections at once"],
    ["False premise", "asks a DHEA dose; the page says DHEA does nothing"],
    ["Negation", "which ingredients have no evidence behind them"],
    ["Terse · misspelled · acronym", "“creatin monohidrate”, “HMB or BCAAs”"],
  ];
  kinds.forEach((k, i) => {
    const ky = y + 0.88 + i * 0.33;
    s.addText(k[0], {
      x: 7.26, y: ky, w: 2.1, h: 0.3, margin: 0,
      fontFace: F.body, fontSize: 9.5, bold: true, color: C.orange, valign: "top",
    });
    s.addText(k[1], {
      x: 9.42, y: ky, w: 3.1, h: 0.34, margin: 0,
      fontFace: F.body, fontSize: 9, color: C.muteDark, valign: "top", lineSpacing: 11.5,
    });
  });

  s.addText(
    "The golden file holds only the question and a reference answer. The contexts and the answer come from the live pipeline at run time — which is what makes the numbers worth having: they move when the pipeline changes.",
    {
      x: 7.26, y: y + 2.9, w: 5.2, h: 0.6, margin: 0,
      fontFace: F.body, fontSize: 9.5, italic: true, color: C.mute, lineSpacing: 12.5,
    }
  );

  s.addText(
    "Cost of one run: 34 questions × 4 metrics = 136 judge calls, ~23 minutes of scoring on top of ~10 minutes of collection.",
    {
      x: M, y: y + 3.84, w: W - M * 2, h: 0.3, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: C.mute,
    }
  );

  // ======================================================================= //
  // 22 — RESULT 1: THE PROMPT FIX
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Result · the prompt fix", "Same questions, same index, same judge. Only the prompt changed.");

  s.addChart(pres.ChartType.bar, [
    { name: "Before", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.613, 0.747, 0.592, 0.582] },
    { name: "After", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.628, 0.793, 0.770, 0.736] },
  ], K.chartFrame({
    x: M, y: y + 0.04, w: 7.5, h: 2.62,
    chartColors: [C.rule, C.ink],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.mute, dataLabelFormatCode: "0.000",
    showLegend: true, legendPos: "b", legendFontFace: F.body, legendFontSize: 10, legendColor: C.mute,
    valAxisMaxVal: 1, valAxisMinVal: 0, valAxisMajorUnit: 0.25,
    barGapWidthPct: 45, catAxisLabelFontSize: 9.5,
  }));

  K.card(s, { x: 8.36, y: y + 0.04, w: W - M - 8.36, h: 1.86, fill: C.tint });
  s.addText("The control that makes it credible", {
    x: 8.62, y: y + 0.2, w: 3.9, h: 0.28, margin: 0,
    fontFace: F.head, fontSize: 13.5, bold: true, color: C.ink,
  });
  s.addText(
    "Context recall barely moved: +0.015. A prompt cannot change what retrieval fetched, so a large movement there would have meant something else was varying between the runs.\n\n" +
    "The two answering metrics moved by an order of magnitude more — which is exactly the shape the fix predicted.",
    {
      x: 8.62, y: y + 0.54, w: 3.9, h: 1.28, margin: 0,
      fontFace: F.body, fontSize: 10, color: "46566B", valign: "top", lineSpacing: 13.5,
    }
  );

  const deltas = [
    ["faithfulness", "+0.177", C.green],
    ["answer relevancy", "+0.154", C.green],
    ["refusals", "12 → 5", C.green],
    ["zero scores of 136", "27 → 10", C.green],
  ];
  deltas.forEach((d, i) => {
    const dy = y + 2.04 + i * 0.44;
    s.addText(d[0], {
      x: 8.42, y: dy, w: 2.5, h: 0.36, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10.5, color: "46566B",
    });
    s.addText(d[1], {
      x: 10.92, y: dy, w: 1.6, h: 0.36, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 15, bold: true, color: d[2],   // arrows: see note above
    });
  });

  s.addText(
    "Why the original 3-question set could never have caught this: all three were simple single-topic lookups. The failure only appears on multi-part, comparative and false-premise questions — which is exactly what the expanded set added.",
    {
      x: M, y: y + 2.9, w: 7.5, h: 0.62, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  // ======================================================================= //
  // 23 — RESULT 2: DEPTH
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Result · retrieval depth", "top_k 5 against 10 — a real trade-off, not a free win");

  s.addChart(pres.ChartType.bar, [
    { name: "top_k = 5", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.628, 0.793, 0.770, 0.736] },
    { name: "top_k = 10", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.781, 0.714, 0.786, 0.688] },
  ], K.chartFrame({
    x: M, y: y + 0.04, w: 7.1, h: 2.5,
    chartColors: [C.rule, C.orange],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.mute, dataLabelFormatCode: "0.000",
    showLegend: true, legendPos: "b", legendFontFace: F.body, legendFontSize: 10, legendColor: C.mute,
    valAxisMaxVal: 1, valAxisMinVal: 0, valAxisMajorUnit: 0.25,
    barGapWidthPct: 45, catAxisLabelFontSize: 9.5,
  }));

  s.addText(
    [
      { text: "Recall rises 0.152 and faithfulness edges up; precision falls 0.079 and relevancy 0.048. ", options: { bold: true, color: C.ink } },
      { text: "Ten chunks per question means more of them are off-topic, and a longer answer is a more diluted one.", options: { color: "46566B" } },
    ],
    {
      x: M, y: y + 2.64, w: 7.1, h: 0.5, margin: 0,
      fontFace: F.body, fontSize: 10.5, valign: "top", lineSpacing: 14,
    }
  );

  s.addText("The questions that moved are the edge cases we added", {
    x: 7.94, y: y + 0.04, w: W - M - 7.94, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 13, bold: true, color: C.ink,
  });

  const moved = [
    ["#13", "0.00 → 1.00", "misspelling — “creatin monohidrate”"],
    ["#23", "0.50 → 1.00", "multi-part: three supplements, one athlete"],
    ["#22", "0.57 → 1.00", "synonym mismatch — baking soda"],
    ["#19", "0.57 → 1.00", "near-miss — tart cherry vs quercetin"],
    ["#18", "0.60 → 1.00", "acronym comparative — HMB vs BCAAs"],
  ];
  moved.forEach((m, i) => {
    const my = y + 0.54 + i * 0.5;
    s.addText(m[0], {
      x: 7.94, y: my, w: 0.5, h: 0.44, margin: 0, valign: "middle",
      fontFace: F.mono, fontSize: 9.5, bold: true, color: C.mute,
    });
    s.addText(m[1], {
      x: 8.42, y: my, w: 1.3, h: 0.44, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10.5, bold: true, color: C.green,
    });
    s.addText(m[2], {
      x: 9.74, y: my, w: 2.9, h: 0.44, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 9, color: "46566B", lineSpacing: 11.5,
    });
  });

  K.card(s, { x: 7.94, y: y + 2.98, w: W - M - 7.94, h: 1.3, fill: C.ink, line: C.ink });
  s.addText("The decision", {
    x: 8.2, y: y + 3.12, w: 4.2, h: 0.24, margin: 0,
    fontFace: F.body, fontSize: 9.5, bold: true, charSpacing: 0.8, color: C.orange,
  });
  s.addText(
    "For a system whose job is citable answers, recall beats precision: a retrieved chunk that goes unused costs little, while evidence never retrieved can never be cited. top_k now defaults to 10 — with the measurement recorded in the code, so the number does not read as taste.",
    {
      x: 8.2, y: y + 3.36, w: 4.2, h: 0.86, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: C.muteDark, valign: "top", lineSpacing: 12.5,
    }
  );

  K.card(s, { x: M, y: y + 3.2, w: 7.1, h: 1.08, fill: "FFF6EC", line: "F0DCC2" });
  s.addText(
    [
      { text: "And it disproved one of our own conclusions. ", options: { bold: true, color: C.ink } },
      { text: "We had written up #13 as “the misspelling defeats retrieval outright”. It does not: at depth 5 the right chunks were being found and ranked below the cutoff. The embedder handled the misspelling; the ranking did not surface it. Spelling-tolerant retrieval went from a planned next step to low priority.", options: { color: "5A4A38" } },
    ],
    {
      x: M + 0.24, y: y + 3.34, w: 6.62, h: 0.84, margin: 0,
      fontFace: F.body, fontSize: 9.5, valign: "top", lineSpacing: 12.5,
    }
  );

  // ======================================================================= //
  // 24 — RESULT: RERANKING
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Result · reranking", "Eight points of precision, bought with three of recall");

  s.addChart(pres.ChartType.bar, [
    { name: "Dense only", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.851, 0.735, 0.870, 0.768] },
    { name: "With reranking", labels: ["Context\nrecall", "Context\nprecision", "Faithfulness", "Answer\nrelevancy"], values: [0.816, 0.819, 0.838, 0.783] },
  ], K.chartFrame({
    x: M, y: y + 0.04, w: 7.2, h: 2.56,
    chartColors: [C.rule, C.green],
    showValue: true, dataLabelPosition: "outEnd", dataLabelColor: C.mute, dataLabelFormatCode: "0.000",
    showLegend: true, legendPos: "b", legendFontFace: F.body, legendFontSize: 10, legendColor: C.mute,
    valAxisMaxVal: 1, valAxisMinVal: 0, valAxisMajorUnit: 0.25,
    barGapWidthPct: 45, catAxisLabelFontSize: 9.5,
  }));

  s.addText("Over the 31 answerable questions. Both runs on the same pinned endpoint, same index, prompt, depth and judge — only reranking changed.", {
    x: M, y: y + 2.66, w: 7.2, h: 0.34, margin: 0,
    fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute,
  });

  const rrows = [
    ["context precision", "0.735 → 0.819", C.green, "the target, and the metric that was failing"],
    ["answer relevancy", "0.768 → 0.783", C.green, "a cleaner context, a less diluted answer"],
    ["context recall", "0.851 → 0.816", C.red, "the cost — it drops chunks dense had kept"],
    ["faithfulness", "0.870 → 0.838", C.red, "the same cost, on groundedness"],
  ];
  rrows.forEach((r, i) => {
    const ry = y + 0.08 + i * 0.62;
    s.addText(r[0], {
      x: 8.02, y: ry, w: 1.9, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 10, color: C.mute,
    });
    // Calibri, not the display serif: Cambria has no U+2192 and substitutes a
    // dash for it, which turns "0.739 → 0.819" into a subtraction.
    s.addText(r[1], {
      x: 8.02, y: ry + 0.24, w: 1.9, h: 0.3, margin: 0,
      fontFace: F.body, fontSize: 14, bold: true, color: r[2],
    });
    s.addText(r[3], {
      x: 10.02, y: ry + 0.1, w: W - M - 10.02, h: 0.42, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: "46566B", valign: "top", lineSpacing: 12,
    });
  });

  K.card(s, { x: 7.94, y: y + 2.6, w: W - M - 7.94, h: 1.42, fill: C.tint });
  s.addText("What the control corrected", {
    x: 8.2, y: y + 2.72, w: 4.3, h: 0.26, margin: 0,
    fontFace: F.head, fontSize: 12.5, bold: true, color: C.ink,
  });
  s.addText(
    "Against the local baseline recall looked flat, and we nearly reported that as proof. A control run on the same endpoint shows it is not: reranking picks which ten of twenty reach the answer, so it can drop one dense had kept. Three points of recall and groundedness buy eight of precision.",
    {
      x: 8.2, y: y + 3.0, w: 4.3, h: 0.94, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: "46566B", valign: "top", lineSpacing: 12.5,
    }
  );

  s.addText(
    "Failing samples 26 → 21. The host move itself was worth +0.029 recall and +0.026 relevancy with no code change — which is exactly why the control was needed before attributing anything to the reranker.",
    {
      x: M, y: y + 3.16, w: 7.2, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", lineSpacing: 14,
    }
  );

  // ======================================================================= //
  // 25 — WHERE WE STAND
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Where we stand", "Three of four metrics pass. The fourth we are not going to round up.");

  s.addText("Shipped configuration · top_k = 10, fixed prompt, reranking on · 31 answerable questions", {
    x: M, y: y - 0.02, w: W - M * 2, h: 0.28, margin: 0,
    fontFace: F.body, fontSize: 11, italic: true, color: C.mute,
  });

  const stand = [
    ["0.838", "faithfulness", true],
    ["0.819", "context precision", true],
    ["0.817", "context recall", true],
    ["0.783", "answer relevancy", false],
  ];
  const stw = (W - M * 2 - 0.63) / 4;
  stand.forEach((st, i) => {
    const x = M + i * (stw + 0.21);
    K.card(s, { x, y: y + 0.32, w: stw, h: 1.42, fill: st[2] ? "EDF6F2" : C.tint, line: st[2] ? "C6E4D8" : C.tintDeep });
    s.addText(st[0], {
      x: x + 0.24, y: y + 0.5, w: stw - 0.48, h: 0.6, margin: 0,
      fontFace: F.head, fontSize: 34, bold: true, color: st[2] ? C.green : C.ink, valign: "middle",
    });
    s.addText(st[1], {
      x: x + 0.24, y: y + 1.1, w: stw - 0.48, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: C.mute,
    });
    K.pill(s, st[2] ? "PASS" : "BELOW 0.80", {
      x: x + 0.24, y: y + 1.38, fill: st[2] ? C.green : C.mute,
    });
  });

  s.addText(
    "Over all 34 questions, including the three that are unanswerable by design: 0.799 recall · 0.754 precision · 0.764 faithfulness · 0.725 relevancy. Failing samples fell from 25 to 21, and answer relevancy is the one metric still short.",
    {
      x: M, y: y + 1.88, w: W - M * 2, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", lineSpacing: 14,
    }
  );

  s.addText("Open, in the order we would do it", {
    x: M, y: y + 2.4, w: 6.0, h: 0.28, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });

  const open = [
    ["Measure a depth between 5 and 10", "Untested, and with reranking now recovering precision, a shallower cut may cost less than it did before."],
    ["Answer relevancy, the last metric", "0.783 against a 0.80 threshold. The judge samples three generated questions per answer and often gets one, so part of the gap is measurement noise rather than the answer."],
    ["Negation and absent-value queries", "#20 asks which ingredients have no evidence; #11 asks for a value the page never states. Retrieving more chunks cannot surface an absence."],
    ["Hybrid BM25 for dosage queries", "Measured at 5.5% of evidence that dense missed, concentrated in numeric questions. Worth adding — just not first."],
  ];
  open.forEach((o, i) => {
    const oy = y + 2.74 + i * 0.46;
    K.chip(s, i + 1, M, oy, { diam: 0.26, size: 10, fill: i < 2 ? C.orange : C.mute });
    s.addText(o[0], {
      x: M + 0.38, y: oy - 0.02, w: 3.1, h: 0.3, margin: 0,
      fontFace: F.body, fontSize: 10, bold: true, color: C.ink,
    });
    s.addText(o[1], {
      x: M + 3.5, y: oy - 0.02, w: W - M - 3.5 - M, h: 0.32, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: "46566B", valign: "top", lineSpacing: 12,
    });
  });

  // ======================================================================= //
  // 26 — HURDLES
  // ======================================================================= //
  s = pres.addSlide();
  K.dark(s);
  y = K.title(s, "What went wrong", "Nineteen hurdles logged. Three of them were our own reasoning.", { dark: true });

  const hurdles = [
    ["EXTERNAL", "The PDF the work assumed does not exist", "NIH publishes it as a web page only — all 29 PDF links on it are cited references. We typeset our own source document and checked it in, so the corpus is reproducible.", C.orange],
    ["DEFECT", "Running heads deleted real headings", "Repetition alone is not a running head when 21 ingredients each have an “Efficacy” section. Position fixed it: 36 → 95 headings.", C.red],
    ["DEFECT", "A stale cache was served as PDF output", "Cache consulted before the source was validated. 288 chunks silently carried no page numbers. Nothing raised.", C.red],
    ["DEFECT", "Half the citations bypassed verification", "Fullwidth brackets from the model slipped past an ASCII-only pattern in 11 of 22 answers.", C.red],
    ["INFRASTRUCTURE", "Four evaluation runs destroyed", "ragas scores a failed judge call as 0, so a broken run still produces a complete, confident-looking report. We discarded four — including one where 110 of 136 calls failed.", C.amber],
    ["OUR OWN ANALYSIS", "Two conclusions we had to withdraw", "A baseline comparison silently used a 3-question report instead of the 34-question one; and we called a retrieval failure a spelling problem that the next measurement disproved.", "9FB3C8"],
  ];

  const hw = (W - M * 2 - 0.42) / 3;
  hurdles.forEach((h, i) => {
    const col = i % 3, row = Math.floor(i / 3);
    const x = M + col * (hw + 0.21);
    const hy = y + 0.02 + row * 1.88;
    K.card(s, { x, y: hy, w: hw, h: 1.72, dark: true });
    K.pill(s, h[0], { x: x + 0.22, y: hy + 0.18, fill: h[3], color: h[3] === "9FB3C8" ? C.ink : C.paper });
    s.addText(h[1], {
      x: x + 0.22, y: hy + 0.5, w: hw - 0.44, h: 0.42, margin: 0,
      fontFace: F.head, fontSize: 12.5, bold: true, color: C.paper, valign: "top", lineSpacing: 15,
    });
    s.addText(h[2], {
      x: x + 0.22, y: hy + 0.94, w: hw - 0.44, h: 0.7, margin: 0,
      fontFace: F.body, fontSize: 9, color: C.muteDark, valign: "top", lineSpacing: 11.8,
    });
  });

  s.addText(
    "Every one of these is written up with the evidence that found it and the test that now prevents it. The ones we are least comfortable with are the silent failures — the runs and the chunks that looked fine and were not.",
    {
      x: M, y: y + 3.94, w: W - M * 2, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute, lineSpacing: 14,
    }
  );

  // ======================================================================= //
  // 27 — CLOSING
  // ======================================================================= //
  s = pres.addSlide();
  K.dark(s);

  s.addText("What we would like you to test", {
    x: M, y: 1.0, w: 8.0, h: 0.56, margin: 0,
    fontFace: F.head, fontSize: 32, bold: true, color: C.paper,
  });
  s.addText(
    "Give us a question. Any question from the fact sheet's ~21 ingredients — and then one it cannot possibly answer.",
    {
      x: M, y: 1.68, w: 7.4, h: 0.56, margin: 0,
      fontFace: F.body, fontSize: 14, color: C.muteDark, valign: "top", lineSpacing: 20,
    }
  );

  const asks = [
    ["Ask something comparative", "“HMB or BCAAs for recovery?” — watch the retrieved chunks appear before the answer does."],
    ["Check a citation", "Take any [n, p. X] and open that page of the source PDF. The page came from the index, not the model."],
    ["Try to break it", "Ask for a carbohydrate loading protocol. The fact sheet does not cover it, and the system will tell you so."],
  ];
  const aw = (W - M * 2 - 0.42) / 3;
  asks.forEach((a, i) => {
    const x = M + i * (aw + 0.21);
    K.card(s, { x, y: 2.4, w: aw, h: 1.66, dark: true });
    K.chip(s, i + 1, x + 0.24, 2.62, { diam: 0.32, size: 12 });
    s.addText(a[0], {
      x: x + 0.24, y: 3.04, w: aw - 0.48, h: 0.3, margin: 0,
      fontFace: F.head, fontSize: 13.5, bold: true, color: C.paper,
    });
    s.addText(a[1], {
      x: x + 0.24, y: 3.36, w: aw - 0.48, h: 0.62, margin: 0,
      fontFace: F.body, fontSize: 10, color: C.muteDark, valign: "top", lineSpacing: 13,
    });
  });

  K.mono(s,
    "$  python -m rag.cli query \"Does creatine improve performance?\" --answer\n" +
    "$  python -m evaluation run\n" +
    "$  python tests/test_pipeline.py        # 54 passing\n" +
    "$  python tests/test_evaluation.py      # 12 passing",
    { x: M, y: 4.2, w: 7.6, h: 1.06, fill: C.inkSoft, size: 9.5, lineSpacing: 14 }
  );

  s.addText(
    "Everything on these slides is reproducible from the repository: the source PDF, the golden set, the evaluation reports and the engineering log that records every figure and where it came from.",
    {
      x: 8.44, y: 4.2, w: W - M - 8.44, h: 1.06, margin: 0,
      fontFace: F.body, fontSize: 10, italic: true, color: C.mute, valign: "top", lineSpacing: 13.5,
    }
  );

  s.addNotes("Close on the refusal. It is the least impressive-looking thing the system does and the most important.");
};
