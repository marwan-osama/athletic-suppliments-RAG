"use strict";
/** Slides 1-13: cover, the problem, the solution, the technology, the need. */

const path = require("path");
const fs = require("fs");
const K = require("./lib/kit");
const { C, F, W, M } = K;

function screenFile() {
  const dir = path.join(__dirname, "assets", "screens");
  if (!fs.existsSync(dir)) return null;
  const hit = fs.readdirSync(dir).filter((f) => /\.(png|jpe?g)$/i.test(f)).sort()[0];
  return hit ? path.join(dir, hit) : null;
}

module.exports = function part1(pres) {
  // ======================================================================= //
  // 1 — COVER
  // ======================================================================= //
  let s = pres.addSlide();
  K.dark(s);

  s.addText("AI CLINICAL DECISION SUPPORT LITE  ·  5-DAY HACKATHON  ·  2026", {
    x: M, y: 1.02, w: W - M * 2, h: 0.3, margin: 0,
    fontFace: F.body, fontSize: 11, bold: true, charSpacing: 1.5, color: C.orange,
  });

  s.addText("Evidence-Based\nSupplement Assistant", {
    x: M, y: 1.44, w: 8.6, h: 1.9, margin: 0,
    fontFace: F.head, fontSize: 50, bold: true, color: C.paper,
    valign: "top", lineSpacing: 58,
  });

  s.addText(
    "A retrieval-augmented assistant for sports-nutrition questions, answering only from an " +
    "official NIH fact sheet — and citing the page every claim came from.",
    {
      x: M, y: 3.42, w: 7.5, h: 0.9, margin: 0,
      fontFace: F.body, fontSize: 15, color: C.muteDark, valign: "top", lineSpacing: 22,
    }
  );

  // The motif, stated once at full size: an answer sentence and its citation.
  K.mono(s,
    "Loading is 20 g/day of\ncreatine monohydrate in\nfour portions of 5 g\n[1, p. 19].",
    { x: 9.42, y: 1.5, w: 3.3, h: 1.06, fill: C.inkSoft, size: 10.5, lineSpacing: 16 }
  );
  s.addText("↑  the page is not the model's to invent —\n    it is rewritten from the index", {
    x: 9.42, y: 2.62, w: 3.3, h: 0.6, margin: 0,
    fontFace: F.body, fontSize: 9.5, italic: true, color: C.mute, lineSpacing: 13,
  });

  const facts = [
    ["1,144", "rows indexed\nfrom a 32-page PDF"],
    ["15/15", "page citations\nverified by hand"],
    ["34", "golden questions,\nbuilt to break it"],
    ["68", "automated tests\npassing"],
  ];
  facts.forEach((f, i) => {
    K.stat(s, {
      x: M + i * 2.42, y: 4.62, w: 2.3, value: f[0], label: f[1],
      size: 34, color: C.paper, labelColor: C.mute, labelSize: 10, vh: 0.6,
    });
  });

  s.addNotes(
    "Opening line: 'A language model will answer any supplement question you ask it. " +
    "It will not tell you where the answer came from — and in this domain that is the whole problem.'\n\n" +
    "This deck is deliberately weighted to the retrieval side. Everything on it was measured; " +
    "where a number is unverified we say so."
  );

  // ======================================================================= //
  // 2 — DIVIDER 01
  // ======================================================================= //
  s = pres.addSlide();
  K.divider(s, "01", "Section one", "The problem\nand the challenge",
    "Fluent medical advice is easy. Traceable medical advice is the hard part — and the only kind that is safe to act on.");

  // ======================================================================= //
  // 3 — THE PROBLEM
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  let y = K.title(s, "The problem", "An LLM will answer. It will not tell you where the answer came from.");
  y = K.lede(s, y,
    "Supplement questions are exactly where an ungrounded model is most convincing and least checkable: " +
    "the vocabulary is technical, the claims are quantitative, and the reader has no way to audit them.");

  const problems = [
    {
      n: 1, h: "It sounds like evidence",
      b: "A dose, a loading protocol, a timing window — stated in the register of a clinical guideline, with nothing behind it. The confidence is indistinguishable from the grounded case.",
    },
    {
      n: 2, h: "It accepts a false premise",
      b: "Ask “since DHEA raises testosterone, what dose should athletes take?” and a helpful model supplies one. The NIH fact sheet says DHEA does not improve performance at all.",
    },
    {
      n: 3, h: "It cannot be audited",
      b: "A coach, dietitian or clinician cannot check a claim they cannot trace. Without a document, a section and a page, review is impossible and the answer is unusable in practice.",
    },
  ];

  const cw = (W - M * 2 - 0.42) / 3;
  problems.forEach((p, i) => {
    const x = M + i * (cw + 0.21);
    K.card(s, { x, y: y + 0.06, w: cw, h: 2.42 });
    K.chip(s, p.n, x + 0.26, y + 0.32);
    s.addText(p.h, {
      x: x + 0.26, y: y + 0.82, w: cw - 0.52, h: 0.36, margin: 0,
      fontFace: F.head, fontSize: 15.5, bold: true, color: C.ink,
    });
    s.addText(p.b, {
      x: x + 0.26, y: y + 1.2, w: cw - 0.52, h: 1.14, margin: 0,
      fontFace: F.body, fontSize: 11.5, color: "39485C", valign: "top", lineSpacing: 15.5,
    });
  });

  s.addText(
    "Three of our 34 evaluation questions are ones the source document cannot answer. " +
    "A system with no refusal path answers all three — fluently, and from nowhere.",
    {
      x: M, y: y + 2.66, w: W - M * 2, h: 0.44, margin: 0,
      fontFace: F.body, fontSize: 12, italic: true, color: C.mute, lineSpacing: 16,
    }
  );

  s.addNotes("The DHEA example is question 21 in our golden set. Our system refuses it — slide on the safety layer shows why that took work to get right.");

  // ======================================================================= //
  // 4 — THE CHALLENGE / THE BRIEF
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The challenge", "Four layers, and a scorecard that says which ones matter");

  const layers = [
    ["Document ingestion", "PDF parsing, section-aware chunking, vector indexing, and metadata carrying document, section and page."],
    ["Retrieval", "Semantic search that is tuned, logged, and transparent — the chunks are shown before anything is generated."],
    ["Generation", "Strict grounding prompts, no outside knowledge, and citations formatted so a claim can be traced."],
    ["Safety", "Detect unsupported claims, and refuse when the retrieved evidence does not carry the question."],
  ];

  layers.forEach((l, i) => {
    const ly = y + 0.06 + i * 0.83;
    K.chip(s, i + 1, M, ly + 0.08, { diam: 0.34, size: 12.5 });
    s.addText(l[0], {
      x: M + 0.48, y: ly, w: 2.5, h: 0.3, margin: 0,
      fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
    });
    s.addText(l[1], {
      x: M + 0.48, y: ly + 0.3, w: 5.5, h: 0.5, margin: 0,
      fontFace: F.body, fontSize: 11, color: "46566B", valign: "top", lineSpacing: 14.5,
    });
  });

  const scored = [
    { label: "Retrieval precision", pts: 30 },
    { label: "Grounding & citations", pts: 25 },
    { label: "Architecture design", pts: 15 },
    { label: "Evaluation metrics", pts: 15 },
    { label: "Clinical safety", pts: 10 },
    { label: "UX & live demo", pts: 5 },
  ];

  K.card(s, { x: 6.68, y: y + 0.02, w: W - M - 6.68, h: 3.42, fill: C.tint });
  s.addText("How the work is judged", {
    x: 6.98, y: y + 0.22, w: 3.2, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });
  s.addText("100 points", {
    x: W - M - 1.3, y: y + 0.24, w: 1.0, h: 0.28, margin: 0, align: "right",
    fontFace: F.body, fontSize: 11, bold: true, color: C.orange,
  });

  s.addChart(pres.ChartType.bar, [{
    name: "Points",
    labels: scored.map((x) => x.label),
    values: scored.map((x) => x.pts),
  }], K.chartFrame({
    x: 6.86, y: y + 0.56, w: W - M - 6.98, h: 2.78,
    barDir: "bar",
    chartColors: [C.orange, C.orange, C.inkLine, C.inkLine, C.inkLine, C.inkLine],
    showValue: true,
    dataLabelPosition: "outEnd",
    dataLabelColor: C.mute,
    valAxisHidden: true,
    valGridLine: { style: "none" },
    valAxisMaxVal: 34,
    barGapWidthPct: 42,
    catAxisLabelFontSize: 10,
  }));

  s.addText(
    "55 of the 100 points are retrieval precision and grounded citation. That is where this deck spends its time, and where the system was built and measured first.",
    {
      x: M, y: y + 3.56, w: W - M * 2, h: 0.42, margin: 0,
      fontFace: F.body, fontSize: 12, italic: true, color: C.mute, lineSpacing: 16,
    }
  );

  // ======================================================================= //
  // 5 — DIVIDER 02
  // ======================================================================= //
  s = pres.addSlide();
  K.divider(s, "02", "Section two", "The proposed\nsolution",
    "One document, read properly. Every claim carrying the page it came from. A refusal when the page does not say.");

  // ======================================================================= //
  // 6 — THE SOLUTION
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Proposed solution", "A closed-corpus assistant with page-level provenance");
  y = K.lede(s, y,
    "The corpus is the NIH Office of Dietary Supplements fact sheet “Dietary Supplements for Exercise " +
    "and Athletic Performance” — 32 pages, ~21 ingredients, public domain.");

  const stages = ["Read PDF", "Clean", "Chunk", "Generate\nquestions", "Embed", "Index"];
  const qstages = ["Expand", "Retrieve", "Rerank", "Answer"];
  const bw = 1.32, bh = 0.62;

  s.addText("BUILD  ·  once per document", {
    x: M, y: y + 0.04, w: 5, h: 0.24, margin: 0,
    fontFace: F.body, fontSize: 9.5, bold: true, charSpacing: 1.1, color: C.mute,
  });
  stages.forEach((t, i) => {
    const x = M + i * (bw + 0.16);
    K.card(s, { x, y: y + 0.32, w: bw, h: bh, fill: C.tint, flat: true });
    s.addText(t, {
      x, y: y + 0.32, w: bw, h: bh, margin: 0, align: "center", valign: "middle",
      fontFace: F.body, fontSize: 10.5, bold: true, color: C.ink, lineSpacing: 12,
    });
    if (i < stages.length - 1) {
      s.addText("›", {
        x: x + bw, y: y + 0.32, w: 0.16, h: bh, margin: 0, align: "center", valign: "middle",
        fontFace: F.body, fontSize: 15, bold: true, color: C.rule,
      });
    }
  });

  s.addText("QUERY  ·  every question", {
    x: M, y: y + 1.14, w: 5, h: 0.24, margin: 0,
    fontFace: F.body, fontSize: 9.5, bold: true, charSpacing: 1.1, color: C.orange,
  });
  qstages.forEach((t, i) => {
    const x = M + i * (bw + 0.16);
    K.card(s, { x, y: y + 1.42, w: bw, h: bh, fill: C.ink, line: C.ink, flat: true });
    s.addText(t, {
      x, y: y + 1.42, w: bw, h: bh, margin: 0, align: "center", valign: "middle",
      fontFace: F.body, fontSize: 10.5, bold: true, color: C.paper,
    });
    if (i < qstages.length - 1) {
      s.addText("›", {
        x: x + bw, y: y + 1.42, w: 0.16, h: bh, margin: 0, align: "center", valign: "middle",
        fontFace: F.body, fontSize: 15, bold: true, color: C.rule,
      });
    }
  });

  const guarantees = [
    ["Closed corpus", "The model may use the retrieved sources and nothing else — no outside knowledge, no inference beyond what the text states."],
    ["Page-level provenance", "Every claim carries [n, p. X]. The page is looked up from the index after generation, not copied by the model."],
    ["A narrow refusal", "Reserved for retrieval that turned up nothing bearing on the question. A grounded partial answer beats a refusal."],
  ];
  const gw = (W - M * 2 - 0.42) / 3;
  guarantees.forEach((g, i) => {
    const x = M + i * (gw + 0.21);
    K.card(s, { x, y: y + 2.3, w: gw, h: 1.5 });
    K.pill(s, "GUARANTEE", { x: x + 0.24, y: y + 2.48, fill: C.green });
    s.addText(g[0], {
      x: x + 0.24, y: y + 2.78, w: gw - 0.48, h: 0.3, margin: 0,
      fontFace: F.head, fontSize: 14, bold: true, color: C.ink,
    });
    s.addText(g[1], {
      x: x + 0.24, y: y + 3.08, w: gw - 0.48, h: 0.68, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
    });
  });

  // ======================================================================= //
  // 7 — WHAT AN ANSWER LOOKS LIKE  (real system output)
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The answer contract", "Real output, and the evidence it was built from");

  s.addText("Q  ·  Does creatine supplementation improve high-intensity exercise performance?", {
    x: M, y: y - 0.02, w: W - M * 2, h: 0.3, margin: 0,
    fontFace: F.body, fontSize: 12.5, bold: true, color: C.ink,
  });

  K.mono(s,
    "Yes. Multiple studies cited in the sources show that creatine\n" +
    "supplementation improves performance during high-intensity,\n" +
    "short-duration exercise such as sprinting and weight-lifting.\n\n" +
    "* In a randomized study of 14 female collegiate soccer\n" +
    "  players, those who received creatine had significantly\n" +
    "  greater increases in muscle strength [1, p. 18].\n\n" +
    "* A short-term trial (5-7 days) found improved peak power\n" +
    "  output during jump squats, and better 100-m sprint\n" +
    "  performance than placebo [6, p. 18].\n\n" +
    "* Position statements of the ACSM, NSCA and ISSN state that\n" +
    "  creatine enhances performance during cycles of high-\n" +
    "  intensity exercise with short recovery [1, p. 19].",
    { x: M, y: y + 0.34, w: 7.5, h: 3.06, size: 9.5, lineSpacing: 13.6 }
  );

  s.addText("Retrieved first — shown before anything is generated", {
    x: 8.36, y: y + 0.34, w: W - M - 8.36, h: 0.26, margin: 0,
    fontFace: F.body, fontSize: 9.5, bold: true, charSpacing: 0.6, color: C.mute,
  });

  const hits = [
    ["Creatine > Efficacy", "p. 18", "0.750", "question"],
    ["Creatine", "p. 17", "0.742", "question"],
    ["Creatine > Efficacy", "p. 18", "0.715", "chunk"],
    ["Creatine > Implications for use", "p. 19", "0.709", "chunk"],
  ];
  hits.forEach((h, i) => {
    const hy = y + 0.68 + i * 0.63;
    K.card(s, { x: 8.36, y: hy, w: W - M - 8.36, h: 0.55, fill: C.tint, flat: true });
    s.addText(h[0], {
      x: 8.5, y: hy + 0.05, w: 3.2, h: 0.22, margin: 0,
      fontFace: F.body, fontSize: 10, bold: true, color: C.ink,
    });
    s.addText(`${h[1]}  ·  sim ${h[2]}  ·  matched on ${h[3]}`, {
      x: 8.5, y: hy + 0.27, w: 3.5, h: 0.22, margin: 0,
      fontFace: F.mono, fontSize: 8.5, color: C.mute,
    });
  });

  const scoreRow = [["context recall", "1.00"], ["faithfulness", "1.00"], ["precision", "0.82"], ["relevancy", "0.92"]];
  scoreRow.forEach((sc, i) => {
    s.addText(sc[1], {
      x: 8.42 + i * 1.06, y: y + 3.22, w: 1.0, h: 0.28, margin: 0,
      fontFace: F.head, fontSize: 15, bold: true, color: C.green, align: "center",
    });
    s.addText(sc[0], {
      x: 8.36 + i * 1.06, y: y + 3.5, w: 1.12, h: 0.24, margin: 0,
      fontFace: F.body, fontSize: 7.5, color: C.mute, align: "center",
    });
  });

  s.addText(
    "Judge-scored, question 1 of the golden set. “Matched on question” means the hit came through a hypothetical question generated for that chunk at build time, not the chunk text itself.",
    {
      x: M, y: y + 3.52, w: 7.5, h: 0.5, margin: 0,
      fontFace: F.body, fontSize: 10, italic: true, color: C.mute, lineSpacing: 13.5,
    }
  );

  // ======================================================================= //
  // 8 — THE APP
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The product", "What it looks like in the hand");

  const shot = screenFile();
  if (shot) {
    s.addImage({
      path: shot, x: M, y: y + 0.04, w: 8.2, h: 3.72,
      sizing: { type: "contain", w: 8.2, h: 3.72 },
    });
  } else {
    K.card(s, { x: M, y: y + 0.04, w: 8.2, h: 3.72, fill: C.tint });
    s.addText(
      "App screens\n\nDrop the mockup PNG into presentation/assets/screens/ and rebuild — it lands here at full width.",
      {
        x: M + 0.6, y: y + 1.4, w: 7.0, h: 1.2, margin: 0, align: "center",
        fontFace: F.body, fontSize: 12, color: C.mute, lineSpacing: 18,
      }
    );
  }

  const ux = [
    ["Evidence before prose", "The Sources screen lists the retrieved passages, their section path and their page — the reader can check the system before trusting it."],
    ["Strength is shown, not implied", "Each ingredient carries an evidence badge drawn from what the fact sheet actually says, including “limited” and “no benefit”."],
    ["Comparison is a first-class view", "The questions people actually ask are comparative. The compare screen answers them side by side, from the same corpus."],
  ];
  ux.forEach((u, i) => {
    const uy = y + 0.06 + i * 1.28;
    K.chip(s, i + 1, 9.0, uy + 0.04, { diam: 0.32, size: 12 });
    s.addText(u[0], {
      x: 9.44, y: uy, w: W - M - 9.44, h: 0.28, margin: 0,
      fontFace: F.head, fontSize: 13.5, bold: true, color: C.ink,
    });
    s.addText(u[1], {
      x: 9.44, y: uy + 0.3, w: W - M - 9.44, h: 0.86, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
    });
  });

  s.addNotes("Live demo goes here: take a judge-provided query, show the retrieved chunks first, then the answer with citations, then an out-of-scope query to show the refusal.");

  // ======================================================================= //
  // 9 — DIVIDER 03
  // ======================================================================= //
  s = pres.addSlide();
  K.divider(s, "03", "Section three", "The technology\nwe used",
    "Every model runs locally. No key, no quota, and no user's health question leaves the machine.");

  // ======================================================================= //
  // 10 — THE STACK
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Used technology", "Chosen for provenance, licensing and portability");

  const rows = [
    ["Ingestion", "pdfplumber", "Exposes per-character font size — the signal we rebuild headings from. Chosen over PyMuPDF specifically to avoid its AGPL licensing."],
    ["Chunking", "langchain-text-splitters", "Heading-aware splitting, so no chunk mixes two ingredients and every chunk states its own subject."],
    ["Embeddings", "EmbeddingGemma-300m", "768 dims, unit-normalised, asymmetric. Its own instruction templates separate a match from a mismatch by 0.47, against 0.35 with no prefixes."],
    ["Vector store", "ChromaDB", "Local persistence, metadata filtering, and a collection name derived from every setting that changes the vectors."],
    ["Generation & rerank", "gpt-oss-20b", "Answering, query expansion and listwise reranking, all through one OpenAI-shaped client."],
    ["Evaluation", "ragas", "Four judge-scored metrics. Imported only when a run starts, so the pipeline never depends on it."],
    ["Interfaces", "Streamlit · CLI · mobile", "The Streamlit app exposes every hyperparameter of every stage; the CLI makes runs reproducible."],
  ];

  const rh = 0.46;
  rows.forEach((r, i) => {
    const ry = y + 0.06 + i * rh;
    if (i % 2 === 0) {
      s.addShape("rect", { x: M, y: ry, w: 8.55, h: rh, fill: { color: C.tint }, line: { color: C.tint } });
    }
    s.addText(r[0], {
      x: M + 0.14, y: ry, w: 1.5, h: rh, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10, bold: true, color: C.mute,
    });
    s.addText(r[1], {
      x: M + 1.66, y: ry, w: 1.9, h: rh, margin: 0, valign: "middle",
      fontFace: F.mono, fontSize: 9.5, bold: true, color: C.ink,
    });
    s.addText(r[2], {
      x: M + 3.62, y: ry, w: 5.4, h: rh, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10, color: "46566B", lineSpacing: 12.5,
    });
  });

  K.card(s, { x: 9.42, y: y + 0.06, w: W - M - 9.42, h: 3.16, fill: C.ink, line: C.ink });
  s.addText("Why local models", {
    x: 9.68, y: y + 0.28, w: 2.9, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.paper,
  });
  s.addText(
    [
      { text: "Privacy. ", options: { bold: true, color: C.orange } },
      { text: "A supplement question can be a health question. Nothing is sent to a third party.\n\n", options: { color: C.muteDark } },
      { text: "No quota. ", options: { bold: true, color: C.orange } },
      { text: "A full evaluation run is ~240 model calls. Metered, that shapes what you are willing to measure.\n\n", options: { color: C.muteDark } },
      { text: "Portable. ", options: { bold: true, color: C.orange } },
      { text: "One client speaks the OpenAI shape, so the provider is a base URL and two model ids. This pipeline has run on Gemini, then OpenRouter, now LM Studio.", options: { color: C.muteDark } },
    ],
    {
      x: 9.68, y: y + 0.66, w: 2.9, h: 2.4, margin: 0,
      fontFace: F.body, fontSize: 10, valign: "top", lineSpacing: 13.5,
    }
  );

  // ======================================================================= //
  // 11 — ARCHITECTURE
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Architecture", "One class per stage, and a settings object that owns the index");

  const arch = [
    { layer: "1 · Ingestion", mods: ["PdfReader", "MarkdownCleaner", "MarkdownChunker", "QuestionGenerator", "ServerEmbedder", "VectorIndex"] },
    { layer: "2 · Retrieval", mods: ["QueryExpander", "Retriever", "Reranker"] },
    { layer: "3 · Generation", mods: ["Answerer", "LLMClient"] },
    { layer: "4 · Safety & proof", mods: ["Answerer refusal", "citation rewrite", "EvaluationEngine", "ChunkInspector"] },
  ];

  let ax = M;
  arch.forEach((a, i) => {
    const aw = i === 0 ? 4.0 : i === 3 ? 2.9 : 2.3;
    K.card(s, { x: ax, y: y + 0.06, w: aw, h: 2.16, fill: i === 1 ? C.ink : C.tint, line: i === 1 ? C.ink : C.tintDeep });
    s.addText(a.layer, {
      x: ax + 0.2, y: y + 0.22, w: aw - 0.4, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 10, bold: true, charSpacing: 0.8,
      color: i === 1 ? C.orange : C.mute,
    });
    a.mods.forEach((m, j) => {
      s.addText(m, {
        x: ax + 0.2, y: y + 0.56 + j * 0.26, w: aw - 0.4, h: 0.24, margin: 0,
        fontFace: F.mono, fontSize: 9.5, color: i === 1 ? C.paper : C.ink,
      });
    });
    ax += aw + 0.19;
  });

  s.addText("Stages are callable objects and compose with the pipe operator:", {
    x: M, y: y + 2.4, w: 6.4, h: 0.26, margin: 0,
    fontFace: F.body, fontSize: 11, color: C.mute,
  });
  K.mono(s, "chunks = (PdfReader() | MarkdownCleaner() | MarkdownChunker(600, 100))(source)", {
    x: M, y: y + 2.68, w: 7.6, h: 0.44, size: 9.5,
  });

  K.card(s, { x: 8.42, y: y + 2.36, w: W - M - 8.42, h: 1.14, fill: C.tint });
  s.addText(
    [
      { text: "Settings decides what an index is. ", options: { bold: true, color: C.ink } },
      { text: "Every value that changes the vectors is part of the collection name, so moving a slider builds a separate index instead of corrupting the previous one — and moving it back reuses what you already paid for.", options: { color: "46566B" } },
    ],
    {
      x: 8.66, y: y + 2.52, w: W - M - 8.9, h: 0.86, margin: 0,
      fontFace: F.body, fontSize: 10, valign: "top", lineSpacing: 13.5,
    }
  );

  // ======================================================================= //
  // 12 — DIVIDER 04
  // ======================================================================= //
  s = pres.addSlide();
  K.divider(s, "04", "Section four", "How much this\nis needed",
    "Every figure on the next slide was retrieved from the document the system indexes — and carries the page it came from.");

  // ======================================================================= //
  // 13 — THE NEED
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The degree of need", "The audience is most of the people who train");
  y = K.lede(s, y,
    "These numbers are not from a market deck. They were pulled out of our own index by our own retriever — " +
    "which is the product, demonstrated on itself.");

  const need = [
    ["66%", "of 1,248 US college students\nreported using a dietary supplement", "p. 1"],
    ["41.7%", "of ~21,000 US college athletes\ntake protein products; 14.0% creatine", "p. 1"],
    ["2 in 3", "of 3,887 adult and adolescent\nelite track and field athletes", "p. 1"],
    ["22.8%", "of 106,698 US military personnel (men)\nused bodybuilding supplements", "p. 2"],
  ];

  const nw = (W - M * 2 - 0.63) / 4;
  need.forEach((n, i) => {
    const x = M + i * (nw + 0.21);
    K.card(s, { x, y: y + 0.04, w: nw, h: 1.86 });
    s.addText(n[0], {
      x: x + 0.24, y: y + 0.22, w: nw - 0.48, h: 0.62, margin: 0,
      fontFace: F.head, fontSize: 36, bold: true, color: C.ink, valign: "middle",
    });
    s.addText(n[1], {
      x: x + 0.24, y: y + 0.88, w: nw - 0.48, h: 0.62, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
    });
    s.addText(`[1, ${n[2]}]`, {
      x: x + 0.24, y: y + 1.5, w: nw - 0.48, h: 0.24, margin: 0,
      fontFace: F.mono, fontSize: 9, bold: true, color: C.orange,
    });
  });

  K.card(s, { x: M, y: y + 2.02, w: 6.2, h: 1.54, fill: C.ink, line: C.ink });
  s.addText("And the market is larger than the evidence", {
    x: M + 0.26, y: y + 2.18, w: 5.7, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.paper,
  });
  s.addText(
    "Sports nutrition supplements were $5.67 billion of retail sales in 2016 — 13.8% of the $41.16 billion " +
    "dietary supplement category [1, p. 1]. Spending is not the constraint. Knowing what is actually supported is.",
    {
      x: M + 0.26, y: y + 2.52, w: 5.7, h: 0.94, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: C.muteDark, valign: "top", lineSpacing: 14,
    }
  );

  K.card(s, { x: 7.06, y: y + 2.02, w: W - M - 7.06, h: 1.54, fill: C.tint });
  s.addText("Why more information does not fix it", {
    x: 7.32, y: y + 2.18, w: 5.3, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14.5, bold: true, color: C.ink,
  });
  s.addText(
    "The National Athletic Trainers' Association notes that study outcomes are often equivocal, which makes " +
    "these substances controversial and confusing to use [1, p. 2]. Most trials enrol only conditioned athletes, " +
    "and the market sells blends while the research tests single ingredients [1, p. 2].",
    {
      x: 7.32, y: y + 2.52, w: W - M - 7.58, h: 0.98, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 13.5,
    }
  );

  s.addNotes("Worth saying out loud: we ran these four questions through the live system while writing this slide. That is the point — the citation is checkable, on stage, by a judge.");
};
