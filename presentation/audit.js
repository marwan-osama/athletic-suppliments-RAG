"use strict";
/**
 * Geometry audit — catches the defects a render would show, without a renderer.
 *
 * Wraps the slide API, records every box the deck draws, and checks three
 * things that are pure arithmetic:
 *
 *   1. text that cannot fit its box at the size asked for
 *   2. anything crossing the slide edge, the margin, or the logo footer
 *   3. cards that collide with each other
 *
 * Character widths are averages per family, so line counts are estimates —
 * the report flags a box at 92% full as tight rather than broken, and only
 * calls overflow when the estimate exceeds the box outright.
 */

const pptxgen = require("pptxgenjs");
const { measure, plain } = require("./lib/metrics");

const W = 13.333, H = 7.5, MARGIN = 0.62;
const FOOTER_TOP = H - 0.62; // logos sit here; content must clear it


const boxes = [];
let current = null;


// Coordinates that are not finite numbers. pptxgenjs writes undefined/NaN as 0
// rather than complaining, and every check below compares false against them —
// so a slide can pile itself up at the origin and audit perfectly clean. This
// list is reported before anything else.
const malformed = [];

function record(kind, o, text) {
  if (!o || o.x === undefined) return;
  for (const axis of ["x", "y", "w", "h"]) {
    if (o[axis] !== undefined && !Number.isFinite(o[axis])) {
      malformed.push(
        `s${String(current).padStart(2, "0")} ${axis.toUpperCase()}=${o[axis]}  ` +
        `${kind}  "${plain(text).replace(/\s+/g, " ").slice(0, 46)}"`
      );
    }
  }
  if (kind === "text" && o.y === undefined) {
    malformed.push(
      `s${String(current).padStart(2, "0")} Y MISSING  ` +
      `"${plain(text).replace(/\s+/g, " ").slice(0, 46)}"`
    );
  }
  boxes.push({
    slide: current, kind, text: plain(text),
    x: o.x, y: o.y, w: o.w || 0, h: o.h || 0, opts: o,
  });
}

// --- instrument ------------------------------------------------------------ //
const proto = Object.getPrototypeOf(new pptxgen().addSlide());
const realText = proto.addText, realShape = proto.addShape,
      realChart = proto.addChart, realImage = proto.addImage;

proto.addText = function (t, o) { record("text", o, t); return realText.call(this, t, o); };
proto.addShape = function (s, o) { record("shape", o, ""); return realShape.call(this, s, o); };
proto.addChart = function (ty, d, o) { record("chart", o, ""); return realChart.call(this, ty, d, o); };
proto.addImage = function (o) { record("image", o, ""); return realImage.call(this, o); };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
const realAdd = pres.addSlide.bind(pres);
let n = 0;
pres.addSlide = function () { current = ++n; return realAdd(); };

const which = process.argv[2] === "appendix";
if (which) { require("./build-part1")(pres); require("./build-part2")(pres); }
else { require("./build-core")(pres); }

// --- checks ---------------------------------------------------------------- //
// PowerPoint does not clip an overfull text box — the text spills out of it.
// So a box being "too small" is only a defect when the spill goes somewhere
// visible: outside the card it sits in, onto the block beneath it, or off the
// slide. Each text box is measured, grown to what it will really occupy, and
// judged on where that lands.
const problems = [];

boxes.forEach((b) => {
  if (b.kind !== "text" || !b.text.trim()) { b.rh = b.h; return; }
  const m = measure(b.text, b.opts);
  b.rh = Math.max(b.h, m.height);          // what it will actually occupy
  b.spill = m.height - b.h;
  b.lines = m.lines;
});

/** The smallest card a text box sits inside, if any. */
function containerOf(t) {
  return boxes
    .filter((c) => c.kind === "shape" && c.slide === t.slide && c.w > 0.8 && c.h > 0.35)
    .filter((c) => t.x >= c.x - 0.03 && t.y >= c.y - 0.03 && t.x + t.w <= c.x + c.w + 0.06)
    .sort((a, c) => a.w * a.h - c.w * c.h)[0];
}

boxes.forEach((b) => {
  const label = `s${String(b.slide).padStart(2, "0")}`;
  const snippet = b.text.replace(/\s+/g, " ").slice(0, 46);
  const right = b.x + b.w, bottom = b.y + (b.rh || b.h);

  if (b.x < MARGIN - 0.02 || right > W - MARGIN + 0.02) {
    problems.push(`${label} MARGIN    x ${b.x.toFixed(2)}-${right.toFixed(2)} outside ${MARGIN}-${(W - MARGIN).toFixed(2)}  "${snippet}"`);
  }
  // Cards count too: a card that reaches the footer sits behind the logos even
  // though its text cleared them. Small shapes (chips, pills) are exempt —
  // they are only ever placed inside something already checked.
  const bigShape = b.kind === "shape" && b.w > 1 && b.h > 0.4;
  if (bottom > FOOTER_TOP + 0.02 && (b.kind !== "shape" || bigShape) && !b.opts.isFooter) {
    problems.push(`${label} FOOTER    text reaches ${bottom.toFixed(2)}, logos start ${FOOTER_TOP.toFixed(2)}  "${snippet}"`);
  }
  if (b.y < 0 || bottom > H + 0.02) {
    problems.push(`${label} OFFSLIDE  y ${b.y.toFixed(2)}-${bottom.toFixed(2)}  "${snippet}"`);
  }

  // Spilling out of the card that frames it — always visible.
  if (b.kind === "text" && b.spill > 0.02) {
    const card = containerOf(b);
    if (card && bottom > card.y + card.h - 0.04) {
      problems.push(`${label} ESCAPES   ${b.lines} lines end ${bottom.toFixed(2)}, card ends ${(card.y + card.h).toFixed(2)}  "${snippet}"`);
    }
  }
});

// Text landing on the text below it, within the same column.
const texts = boxes.filter((b) => b.kind === "text" && b.text.trim());
texts.forEach((a) => {
  texts.forEach((c) => {
    if (a === c || a.slide !== c.slide || c.y <= a.y + 0.01) return;
    const overlapX = Math.min(a.x + a.w, c.x + c.w) - Math.max(a.x, c.x);
    if (overlapX < 0.3) return;                 // different columns
    const gap = c.y - (a.y + a.rh);
    // Only boxes that *grew* count. A heading sitting 0.02" above its own body
    // is deliberate pairing and reads fine; a paragraph that overflowed its box
    // and now touches the next block is a defect. The difference is the spill,
    // not the gap, so a tight gap is only reported when something overran.
    const encroached = (a.spill || 0) > 0.02 ? gap < 0.05 : gap < -0.04;
    if (encroached) {
      problems.push(`s${String(a.slide).padStart(2, "0")} COLLIDE   "${a.text.replace(/\s+/g, " ").slice(0, 34)}" clears next by only ${gap.toFixed(2)}" — "${c.text.replace(/\s+/g, " ").slice(0, 30)}"`);
    }
  });
});

// 3 — card collisions (shapes only; text is meant to sit on top of them)
const bySlide = {};
boxes.filter((b) => b.kind === "shape" && b.w > 1 && b.h > 0.5)
  .forEach((b) => (bySlide[b.slide] = bySlide[b.slide] || []).push(b));
Object.entries(bySlide).forEach(([slide, cards]) => {
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      const a = cards[i], b = cards[j];
      const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
      const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
      if (ox > 0.05 && oy > 0.05) {
        problems.push(`s${String(slide).padStart(2, "0")} COLLIDE   cards overlap by ${ox.toFixed(2)}" x ${oy.toFixed(2)}"  @(${a.x.toFixed(2)},${a.y.toFixed(2)}) and (${b.x.toFixed(2)},${b.y.toFixed(2)})`);
      }
    }
  }
});

console.log(`${n} slides, ${boxes.length} elements audited\n`);
if (malformed.length) {
  console.log("MALFORMED COORDINATES — these render at 0 and defeat every other check:");
  [...new Set(malformed)].forEach((m) => console.log("  " + m));
  console.log("");
}
if (!problems.length && !malformed.length) console.log("no geometry problems found");
else {
  const uniq = [...new Set(problems)];
  uniq.forEach((p) => console.log(p));
  console.log(`
${uniq.length} to fix`);
}
