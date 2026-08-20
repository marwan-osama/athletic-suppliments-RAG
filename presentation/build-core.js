"use strict";
/**
 * The judged deck: nine slides, in the order the Day 5 brief asks for.
 *
 *   1 cover · 2 the need · 3 why a model alone will not do · 4 architecture
 *   5-7 the retrieval problem, in three stages · 8 evidence · 9 what is next
 *
 * Figures are given as percentages rather than raw metric decimals: the talk is
 * five to seven minutes and a judge should be able to read a number once and
 * keep listening. The exact values behind every one of them are in
 * docs/engineering-log.md and in the appendix deck.
 */

const path = require("path");
const fs = require("fs");
const K = require("./lib/kit");
const { measure } = require("./lib/metrics");
const { C, F, W, M } = K;

function screenFile() {
  const dir = path.join(__dirname, "assets", "screens");
  if (!fs.existsSync(dir)) return null;
  const hit = fs.readdirSync(dir).filter((f) => /\.(png|jpe?g)$/i.test(f)).sort()[0];
  return hit ? path.join(dir, hit) : null;
}

/** A stage panel for the three-part retrieval story. */
function stagePanel(s, o) {
  K.card(s, { x: o.x, y: o.y, w: o.w, h: o.h, fill: o.fill, line: o.line });
  K.pill(s, o.tag, { x: o.x + 0.24, y: o.y + 0.2, fill: o.tagFill });
  s.addText(o.title, {
    x: o.x + 0.24, y: o.y + 0.54, w: o.w - 0.48, h: 0.46, margin: 0,
    fontFace: F.head, fontSize: 15, bold: true, color: C.ink,
    valign: "top", lineSpacing: 18,
  });
  s.addText(o.body, {
    x: o.x + 0.24, y: o.y + 1.02, w: o.w - 0.48, h: o.bodyH || 1.0, margin: 0,
    fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
  });
}

module.exports = function core(pres) {
  let s, y;

  // ======================================================================= //
  // 1 — COVER
  // ======================================================================= //
  s = pres.addSlide();
  K.dark(s);

  s.addText("AI CLINICAL DECISION SUPPORT LITE  ·  HACKATHON 2026", {
    x: M, y: 1.72, w: W - M * 2, h: 0.3, margin: 0,
    fontFace: F.body, fontSize: 11, bold: true, charSpacing: 1.5, color: C.orange,
  });

  s.addText("Evidence-Based\nSupplement Assistant", {
    x: M, y: 2.14, w: 8.6, h: 1.9, margin: 0,
    fontFace: F.head, fontSize: 50, bold: true, color: C.paper,
    valign: "top", lineSpacing: 58,
  });

  s.addText(
    "Answers sports-nutrition questions from one official NIH fact sheet — and cites the page every claim came from.",
    {
      x: M, y: 4.12, w: 7.6, h: 0.86, margin: 0,
      fontFace: F.body, fontSize: 15, color: C.muteDark, valign: "top", lineSpacing: 22,
    }
  );

  K.mono(s,
    "Loading is 20 g/day of\ncreatine monohydrate in\nfour portions of 5 g\n[1, p. 19].",
    { x: 9.42, y: 2.2, w: 3.3, h: 1.1, fill: C.inkSoft, size: 10.5, lineSpacing: 16 }
  );
  s.addText("↑  the page is checked against the index,\n    never taken from the model", {
    x: 9.42, y: 3.4, w: 3.3, h: 0.6, margin: 0,
    fontFace: F.body, fontSize: 9.5, italic: true, color: C.mute, lineSpacing: 13,
  });

  s.addNotes(
    "Open: 'Two thirds of the athletes in this fact sheet take supplements. Ask a chatbot which ones work "
    + "and it will tell you — fluently, and with nothing behind it. That gap is what we built for.'\n\n"
    + "Five to seven minutes. Problem, why a model alone fails, architecture, the retrieval problem in three "
    + "stages, the evidence, what is next."
  );

  // ======================================================================= //
  // 2 — THE NEED  (business problem)
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The problem", "Most people who train take supplements. Almost none can check them.");

  const need = [
    ["66%", "of surveyed US college\nstudents take a supplement", "p. 1"],
    ["42%", "of ~21,000 college athletes\ntake protein products", "p. 1"],
    ["2 in 3", "elite track and field athletes,\nacross international surveys", "p. 1"],
    ["$5.7bn", "of sports nutrition sold\nin a single year", "p. 1"],
  ];
  const nw = (W - M * 2 - 0.63) / 4;
  need.forEach((n, i) => {
    const x = M + i * (nw + 0.21);
    K.card(s, { x, y: y + 0.04, w: nw, h: 1.78 });
    s.addText(n[0], {
      x: x + 0.24, y: y + 0.2, w: nw - 0.48, h: 0.6, margin: 0,
      fontFace: F.head, fontSize: 34, bold: true, color: C.ink, valign: "middle",
    });
    s.addText(n[1], {
      x: x + 0.24, y: y + 0.84, w: nw - 0.48, h: 0.56, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
    });
    s.addText(`[1, ${n[2]}]`, {
      x: x + 0.24, y: y + 1.44, w: nw - 0.48, h: 0.24, margin: 0,
      fontFace: F.mono, fontSize: 9, bold: true, color: C.orange,
    });
  });

  s.addText(
    "Every figure above was retrieved from the document this system indexes, by this system — which is the product, demonstrated on itself.",
    {
      x: M, y: y + 1.94, w: W - M * 2, h: 0.32, margin: 0,
      fontFace: F.body, fontSize: 11, italic: true, color: C.mute,
    }
  );

  const gaps = [
    ["The evidence is real, and unreadable", "The answers exist — in a 32-page federal fact sheet written for health professionals, dense with study designs, dose ranges and hedged conclusions."],
    ["The market is louder than the evidence", "Products are sold as blends while research tests single ingredients, and labels rarely state how much of each is inside."],
    ["Even the experts hedge", "The National Athletic Trainers' Association notes that study outcomes are often equivocal, which makes these substances controversial and confusing to use [1, p. 2]."],
  ];
  const gw = (W - M * 2 - 0.42) / 3;
  gaps.forEach((g, i) => {
    const x = M + i * (gw + 0.21);
    K.card(s, { x, y: y + 2.38, w: gw, h: 1.5, fill: C.tint, flat: true });
    s.addText(g[0], {
      x: x + 0.24, y: y + 2.54, w: gw - 0.48, h: 0.46, margin: 0,
      fontFace: F.head, fontSize: 13, bold: true, color: C.ink, valign: "top", lineSpacing: 16,
    });
    s.addText(g[1], {
      x: x + 0.24, y: y + 3.0, w: gw - 0.48, h: 0.8, margin: 0,
      fontFace: F.body, fontSize: 10, color: "46566B", valign: "top", lineSpacing: 13,
    });
  });

  s.addNotes("Land the point: the information is public and already paid for by the taxpayer. What is missing is a way to ask it a question and get an answer you can check.");

  // ======================================================================= //
  // 3 — WHY A MODEL ALONE FAILS, AND WHAT RAG CHANGES
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Why a language model alone is not enough", "It will answer. It will not show you where the answer came from.");

  const fails = [
    ["It sounds exactly like evidence", "A dose, a loading protocol, a timing window — delivered in the register of a clinical guideline, with nothing behind it."],
    ["It accepts a false premise", "Ask “since DHEA raises testosterone, what dose should athletes take?” and it supplies one. The fact sheet says DHEA does not improve performance at all."],
    ["It cannot be audited", "A coach or dietitian cannot check a claim they cannot trace. Without a document, a section and a page, review is impossible."],
  ];
  fails.forEach((f, i) => {
    const fy = y + 0.08 + i * 1.12;
    K.chip(s, i + 1, M, fy + 0.02, { diam: 0.32, size: 12, fill: C.red });
    s.addText(f[0], {
      x: M + 0.46, y: fy, w: 5.4, h: 0.3, margin: 0,
      fontFace: F.head, fontSize: 13.5, bold: true, color: C.ink,
    });
    s.addText(f[1], {
      x: M + 0.46, y: fy + 0.32, w: 5.4, h: 0.7, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B", valign: "top", lineSpacing: 14,
    });
  });

  K.card(s, { x: 6.66, y: y + 0.04, w: W - M - 6.66, h: 3.5, fill: C.ink, line: C.ink });
  s.addText("What retrieval changes", {
    x: 6.94, y: y + 0.24, w: 5.4, h: 0.34, margin: 0,
    fontFace: F.head, fontSize: 17, bold: true, color: C.paper,
  });
  s.addText("The model stops being the source of facts and becomes the thing that phrases them.", {
    x: 6.94, y: y + 0.6, w: 5.4, h: 0.5, margin: 0,
    fontFace: F.body, fontSize: 11, italic: true, color: C.muteDark, valign: "top", lineSpacing: 14,
  });

  const fixes = [
    ["Closed corpus", "It may use the retrieved passages and nothing else — no outside knowledge, no inference past what the text states."],
    ["Provenance it cannot fake", "Every claim carries [n, p. X], and the page is looked up from the index after generation. Choosing the source is the model's job; the page is not."],
    ["A refusal that means something", "When retrieval turns up nothing bearing on the question, the answer is that the document does not cover it."],
  ];
  fixes.forEach((f, i) => {
    const fy = y + 1.18 + i * 0.8;
    K.chip(s, i + 1, 6.94, fy + 0.02, { diam: 0.3, size: 11, fill: C.green });
    s.addText(f[0], {
      x: 7.36, y: fy, w: 5.0, h: 0.28, margin: 0,
      fontFace: F.body, fontSize: 12, bold: true, color: C.paper,
    });
    s.addText(f[1], {
      x: 7.36, y: fy + 0.28, w: 5.0, h: 0.48, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: C.muteDark, valign: "top", lineSpacing: 12.5,
    });
  });

  s.addNotes("This is the pivot from business to technical. Say it plainly: we did not make the model smarter, we made it accountable.");

  // ======================================================================= //
  // 4 — ARCHITECTURE
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "Architecture", "Four layers, one class per stage, and an evaluation loop around all of it");

  const pipe = ["PDF", "Parse +\nstructure", "Chunk +\npage tag", "Embed", "Vector\nindex", "Retrieve", "Rerank", "Ground +\ncite", "Answer"];
  const pw = (W - M * 2 - 0.16 * 8) / 9;
  pipe.forEach((t, i) => {
    const x = M + i * (pw + 0.16);
    const isLast = i === pipe.length - 1;
    K.card(s, {
      x, y: y + 0.04, w: pw, h: 0.7, flat: true,
      fill: isLast ? C.green : i >= 5 ? C.ink : C.tint,
      line: isLast ? C.green : i >= 5 ? C.ink : C.tintDeep,
    });
    s.addText(t, {
      x, y: y + 0.04, w: pw, h: 0.7, margin: 0, align: "center", valign: "middle",
      fontFace: F.body, fontSize: 9.5, bold: true,
      color: i >= 5 ? C.paper : C.ink, lineSpacing: 11,
    });
    if (!isLast) {
      s.addText("›", {
        x: x + pw, y: y + 0.04, w: 0.16, h: 0.7, margin: 0, align: "center", valign: "middle",
        fontFace: F.body, fontSize: 14, bold: true, color: C.rule,
      });
    }
  });

  const layers = [
    ["1 · Ingestion", "A PDF carries no headings, only glyphs at coordinates. Font sizes above the body size are ranked into heading levels, recovering 95 sections; each page's text is tagged so every chunk knows its page.", C.tint],
    ["2 · Retrieval", "The query is expanded into other phrasings, searched against 1,144 rows — passages plus questions generated for them — then reordered by a reranker before the cut.", C.tint],
    ["3 · Generation", "Grounding is strict, and the citation the model writes is rewritten against the index, so the page comes from retrieval metadata rather than from the model.", C.tint],
    ["4 · Safety & evaluation", "Refusal when nothing relevant is retrieved, plus a 34-question golden set scored on four metrics — two grading retrieval, two grading the answer.", "EDF6F2"],
  ];
  const lw = (W - M * 2 - 0.63) / 4;
  layers.forEach((l, i) => {
    const x = M + i * (lw + 0.21);
    K.card(s, { x, y: y + 1.06, w: lw, h: 2.3, fill: l[2], line: i === 3 ? "C6E4D8" : C.tintDeep });
    s.addText(l[0], {
      x: x + 0.24, y: y + 1.24, w: lw - 0.48, h: 0.3, margin: 0,
      fontFace: F.body, fontSize: 11, bold: true, charSpacing: 0.6,
      color: i === 3 ? C.green : C.orange,
    });
    s.addText(l[1], {
      x: x + 0.24, y: y + 1.58, w: lw - 0.48, h: 1.6, margin: 0,
      fontFace: F.body, fontSize: 10, color: "46566B", valign: "top", lineSpacing: 13.5,
    });
  });

  s.addText(
    "Everything runs on local models through one OpenAI-shaped client, so no user's health question leaves the machine and swapping providers is a base URL and two model ids.",
    {
      x: M, y: y + 3.5, w: W - M * 2, h: 0.34, margin: 0,
      fontFace: F.body, fontSize: 10.5, italic: true, color: C.mute,
    }
  );

  s.addNotes("If a judge asks about chunk size: 600 characters with 100 overlap, cut at headings so no chunk mixes two ingredients. Tuned on the Chunks tab before paying for any embeddings.");

  // ======================================================================= //
  // 5 — STAGE ONE: SHALLOW RETRIEVAL
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The retrieval problem · 1", "Retrieve a little, and the evidence never reaches the answer");

  y = K.lede(s, y, "We started where most systems start: dense search, take the top five passages, answer from those.");

  stagePanel(s, {
    x: M, y: y + 0.1, w: 5.9, h: 3.4, fill: "FDF1EC", line: "F3D8CB",
    tag: "THE PROBLEM", tagFill: C.red,
    title: "About a third of the needed evidence never arrives",
    body: "Context recall sat in the low sixties — the retriever was finding some of what each answer needed and missing the rest. "
        + "The failures were not random. Comparative questions, multi-part questions and one misspelled query were the ones that broke, "
        + "and the worst of them retrieved nothing useful at all.\n\n"
        + "A passage that is never retrieved cannot be cited, cannot be checked, and cannot appear in the answer. This is the ceiling "
        + "on everything downstream.",
    bodyH: 2.1,
  });

  const bars = [
    ["Context recall — evidence found", 63, C.red],
    ["Never retrieved at all", 37, C.rule],
  ];
  K.card(s, { x: 6.72, y: y + 0.1, w: W - M - 6.72, h: 3.4, fill: C.tint });
  s.addText("Where the evidence went", {
    x: 6.98, y: y + 0.22, w: 5.4, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 14, bold: true, color: C.ink,
  });
  bars.forEach((b, i) => {
    const by = y + 0.9 + i * 1.0;
    s.addText(b[0], {
      x: 6.98, y: by, w: 3.4, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 10.5, color: "46566B",
    });
    s.addShape("rect", {
      x: 6.98, y: by + 0.3, w: 4.6, h: 0.22,
      fill: { color: C.tintDeep }, line: { color: C.tintDeep },
    });
    s.addShape("rect", {
      x: 6.98, y: by + 0.3, w: 4.6 * (b[1] / 100), h: 0.22,
      fill: { color: b[2] }, line: { color: b[2] },
    });
    s.addText(`${b[1]}%`, {
      x: 11.7, y: by + 0.22, w: 0.8, h: 0.36, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 13, bold: true, color: b[2] === C.rule ? C.mute : b[2],
    });
  });
  s.addText("Measured across 34 questions written to stress the retriever, not to flatter it.", {
    x: 6.98, y: y + 3.02, w: 5.4, h: 0.32, margin: 0,
    fontFace: F.body, fontSize: 10, italic: true, color: C.mute,
  });

  // ======================================================================= //
  // 6 — STAGE TWO: DEEPER RETRIEVAL
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The retrieval problem · 2", "Retrieve more, and the answer gets diluted instead");

  y = K.lede(s, y, "So we looked deeper — twice as many passages per question. Recall rose sharply, and a second problem took its place.");

  stagePanel(s, {
    x: M, y: y + 0.1, w: 5.9, h: 3.4, fill: "FFF6EC", line: "F0DCC2",
    tag: "THE NEW PROBLEM", tagFill: C.amber,
    title: "The evidence arrives, buried in what came with it",
    body: "Recall climbed into the mid-eighties and every multi-part and comparative question was answered — including the misspelled one, "
        + "which turned out never to have been a spelling problem. The right passages had been found all along and ranked below the cut.\n\n"
        + "But precision fell into the low seventies: most of what now reached the answerer was off-topic. Answers grew longer, hedged more, "
        + "and drifted from the question asked. Depth bought recall and paid for it in relevance.",
    bodyH: 2.1,
  });

  const tradeoff = [
    ["Context recall", "63%", "85%", C.green],
    ["Context precision", "79%", "74%", C.red],
    ["Answer relevancy", "77%", "77%", C.mute],
  ];
  K.card(s, { x: 6.72, y: y + 0.1, w: W - M - 6.72, h: 3.4, fill: C.tint });
  s.addText("Shallow  →  deeper", {
    x: 6.98, y: y + 0.22, w: 2.5, h: 0.3, margin: 0,
    fontFace: F.body, fontSize: 15, bold: true, color: C.ink,   // sans: Cambria has no U+2192
  });
  s.addText("a real trade, not a free win", {
    x: 9.62, y: y + 0.24, w: 2.8, h: 0.3, margin: 0, align: "right",
    fontFace: F.body, fontSize: 10, italic: true, color: C.mute,
  });
  tradeoff.forEach((t, i) => {
    const ty = y + 0.92 + i * 0.68;
    s.addText(t[0], {
      x: 6.98, y: ty, w: 3.3, h: 0.4, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10.5, color: "46566B",
    });
    s.addText(t[1], {
      x: 10.34, y: ty, w: 0.8, h: 0.4, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 13, color: C.mute,
    });
    s.addText("→", {
      x: 11.16, y: ty, w: 0.4, h: 0.4, margin: 0, valign: "middle", align: "center",
      fontFace: F.body, fontSize: 12, color: C.rule,
    });
    s.addText(t[2], {
      x: 11.56, y: ty, w: 0.9, h: 0.4, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 14, bold: true, color: t[3],
    });
  });
  s.addText("Depth cannot fix ranking. It only moves the cut further down a list that is still in the wrong order.", {
    x: 6.98, y: y + 3.02, w: 5.4, h: 0.36, margin: 0,
    fontFace: F.body, fontSize: 10, italic: true, color: C.mute,
  });

  // ======================================================================= //
  // 7 — STAGE THREE: RERANKING
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "The retrieval problem · 3", "Retrieve deep, then reorder — and keep both");

  y = K.lede(s, y, "Before building anything we measured where the evidence actually sits. Two fifths of it was being retrieved and then ranked too low: a reordering problem, not a recall problem.");

  stagePanel(s, {
    x: M, y: y + 0.1, w: 5.9, h: 3.4, fill: "EDF6F2", line: "C6E4D8",
    tag: "THE FIX", tagFill: C.green,
    title: "Fetch twenty, have the model order them, keep ten",
    body: "The embedder scores a question and a passage separately — neither vector ever sees the other. A reranker reads them together, "
        + "which is why it can tell a passage that shares vocabulary from one that actually answers.\n\n"
        + "Listwise, so a search costs one extra call rather than one per candidate. It reorders and never filters: anything the model "
        + "leaves out keeps its original place behind what it chose, and a failed call falls back to the dense order.",
    bodyH: 2.1,
  });

  K.card(s, { x: 6.72, y: y + 0.1, w: W - M - 6.72, h: 3.4, fill: C.tint });
  s.addText("Measured against the same setup without it", {
    x: 6.98, y: y + 0.2, w: 5.4, h: 0.3, margin: 0,
    fontFace: F.head, fontSize: 13.5, bold: true, color: C.ink,
  });

  const rr = [
    ["Context recall", "85%", "82%", C.red, "−3"],
    ["Context precision", "74%", "82%", C.green, "+8"],
    ["Answer relevancy", "77%", "78%", C.green, "+1"],
  ];
  rr.forEach((r, i) => {
    const ry = y + 0.84 + i * 0.66;
    s.addText(r[0], {
      x: 6.98, y: ry, w: 3.3, h: 0.36, margin: 0, valign: "middle",
      fontFace: F.body, fontSize: 10, color: "46566B",
    });
    s.addText(r[1], {
      x: 10.3, y: ry, w: 0.7, h: 0.36, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 12, color: C.mute,
    });
    s.addText("→", {
      x: 11.02, y: ry, w: 0.36, h: 0.36, margin: 0, valign: "middle", align: "center",
      fontFace: F.body, fontSize: 11, color: C.rule,
    });
    s.addText(r[2], {
      x: 11.38, y: ry, w: 0.72, h: 0.36, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 13.5, bold: true, color: r[3],
    });
    s.addText(r[4], {
      x: 12.12, y: ry, w: 0.5, h: 0.36, margin: 0, valign: "middle", align: "right",
      fontFace: F.body, fontSize: 10, bold: true, color: r[3],
    });
  });

  s.addText(
    [
      { text: "The cost is real and we are not hiding it: ", options: { bold: true, color: C.ink } },
      { text: "reranking decides which ten of the twenty reach the answer, so it can drop one dense had kept. Context recall and faithfulness each give up about three points to buy eight of context precision.", options: { color: "46566B" } },
    ],
    {
      x: 6.98, y: y + 2.9, w: 5.4, h: 0.52, margin: 0,
      fontFace: F.body, fontSize: 9.5, valign: "top", lineSpacing: 12.5,
    }
  );

  s.addNotes("If asked why not a cross-encoder: it would mean pulling in torch against a deliberately light dependency set. The listwise LLM reranker goes through the client we already had, and no new dependency.");

  // ======================================================================= //
  // 8 — EVIDENCE
  // ======================================================================= //
  s = pres.addSlide();
  K.light(s);
  y = K.title(s, "What we can prove", "Four metrics, 34 questions, and the one we still fail");

  const scores = [
    ["87%", "Faithfulness", true, "of the answer's claims are supported by the passages shown"],
    ["82%", "Context precision", true, "of the passages retrieved were relevant to the question"],
    ["82%", "Context recall", true, "of the evidence each answer needed was found"],
    ["78%", "Answer relevancy", false, "how directly the answer addresses the question asked"],
  ];
  const sw = (W - M * 2 - 0.63) / 4;
  scores.forEach((sc, i) => {
    const x = M + i * (sw + 0.21);
    K.card(s, { x, y: y + 0.04, w: sw, h: 1.78, fill: sc[2] ? "EDF6F2" : C.tint, line: sc[2] ? "C6E4D8" : C.tintDeep });
    s.addText(sc[0], {
      x: x + 0.24, y: y + 0.2, w: sw - 0.48, h: 0.6, margin: 0,
      fontFace: F.head, fontSize: 32, bold: true, color: sc[2] ? C.green : C.ink, valign: "middle",
    });
    s.addText(sc[1], {
      x: x + 0.24, y: y + 0.8, w: sw - 0.48, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 11, bold: true, color: C.ink,
    });
    s.addText(sc[3], {
      x: x + 0.24, y: y + 1.06, w: sw - 0.48, h: 0.38, margin: 0,
      fontFace: F.body, fontSize: 9, color: C.mute, valign: "top", lineSpacing: 11.5,
    });
    K.pill(s, sc[2] ? "PASS" : "BELOW 80%", { x: x + 0.24, y: y + 1.44, fill: sc[2] ? C.green : C.mute });
  });

  const proof = [
    ["Success case", "“HMB or BCAAs for recovery?” — the reranker pulls the BCAA passages from ranks 13, 15 and 18 into the top ten, so both halves of the comparison reach the answer, each cited to its page.", C.green],
    ["Refusal case", "Three questions the document cannot answer, plus a false-premise DHEA dose and a value the page never states. All five are declined rather than invented — and the metric scores a correct refusal as a failure, which is why we report it.", C.orange],
    ["The honest limit", "Answer relevancy is short of threshold. Part of it is the judge sampling fewer generated questions than it asks for; part of it is genuinely longer answers than the question needs.", C.mute],
  ];
  const prw = (W - M * 2 - 0.42) / 3;
  proof.forEach((p, i) => {
    const x = M + i * (prw + 0.21);
    K.card(s, { x, y: y + 1.96, w: prw, h: 1.6, fill: C.tint, flat: true });
    K.pill(s, p[0].toUpperCase(), { x: x + 0.22, y: y + 2.12, fill: p[2] });
    s.addText(p[1], {
      x: x + 0.22, y: y + 2.46, w: prw - 0.44, h: 1.0, margin: 0,
      fontFace: F.body, fontSize: 9.5, color: "46566B", valign: "top", lineSpacing: 12.5,
    });
  });

  s.addText(
    "Scored by an LLM judge over a golden set built to break the system: near-miss pairs, multi-hop questions, a negation, a misspelling, and three questions with no answer in the document at all.",
    {
      x: M, y: y + 3.68, w: W - M * 2, h: 0.32, margin: 0,
      fontFace: F.body, fontSize: 10, italic: true, color: C.mute,
    }
  );

  s.addNotes("If a judge asks where it fails: negation questions (which ingredients have no evidence) and questions asking for a value the page never states. Retrieving more chunks cannot surface an absence — that needs a different mechanism, not tuning.");

  // ======================================================================= //
  // 9 — NEXT STEPS
  // ======================================================================= //
  s = pres.addSlide();
  K.dark(s);
  y = K.title(s, "What comes next", "From “what does the evidence say” to “what should I eat”", { dark: true });

  y = K.lede(s, y, "The fact sheet already states doses. The next step is to meet them from food and drink, not only from a tub.", { dark: true });

  const next = [
    ["1", "Match the dose, not just the ingredient",
     "The document gives quantities — around 2 cups of beetroot juice, 3 g/day of HMB, a caffeine range per kilogram of body weight. Those are the numbers a recommendation has to hit."],
    ["2", "Map ingredients onto foods and drinks",
     "Beetroot juice, tart cherry, oily fish, dairy protein, coffee. A food composition source joins to the same ingredient names the index already carries, so provenance survives the join."],
    ["3", "Answer the question people actually ask",
     "“I am a 70 kg cyclist, what should I drink before a time trial?” becomes a portion and a timing, cited to the page that set the dose — and a refusal when the evidence does not support one."],
  ];
  const nw2 = (W - M * 2 - 0.42) / 3;
  next.forEach((n, i) => {
    const x = M + i * (nw2 + 0.21);
    K.card(s, { x, y: y + 0.06, w: nw2, h: 2.14, dark: true });
    K.chip(s, n[0], x + 0.24, y + 0.26, { diam: 0.34, size: 12.5 });
    s.addText(n[1], {
      x: x + 0.24, y: y + 0.74, w: nw2 - 0.48, h: 0.5, margin: 0,
      fontFace: F.head, fontSize: 13.5, bold: true, color: C.paper, valign: "top", lineSpacing: 16,
    });
    s.addText(n[2], {
      x: x + 0.24, y: y + 1.26, w: nw2 - 0.48, h: 0.8, margin: 0,
      fontFace: F.body, fontSize: 10, color: C.muteDark, valign: "top", lineSpacing: 13,
    });
  });

  K.card(s, { x: M, y: y + 2.36, w: W - M * 2, h: 0.92, dark: true, fill: C.inkSoft });
  s.addText(
    [
      { text: "The constraint stays the same. ", options: { bold: true, color: C.orange } },
      { text: "A food recommendation is only as good as the dose behind it, and the dose has to come from the document with its page attached. Nothing gets recommended that the evidence does not carry — which is the same rule that governs every answer the system gives today.", options: { color: C.muteDark } },
    ],
    {
      x: M + 0.26, y: y + 2.52, w: W - M * 2 - 0.52, h: 0.62, margin: 0,
      fontFace: F.body, fontSize: 10.5, valign: "top", lineSpacing: 14,
    }
  );

  s.addNotes("Close here. Then offer the live demo: a judge-chosen question, chunks shown before the answer, then an out-of-scope question to show the refusal.");
};
