"use strict";
/**
 * Text-fit arithmetic, shared by the deck and its audit so both agree.
 *
 * There is no font engine here — advances are averages measured across a mixed
 * alphabet, so a line count is an estimate. It is used two ways: the kit sizes
 * title and standfirst boxes from it, and the audit flags anything whose
 * estimate does not fit. Both err the same direction.
 */

const ADVANCE = { "Calibri": 0.478, "Cambria": 0.505, "Courier New": 0.600 };

function plain(text) {
  if (typeof text === "string") return text;
  if (Array.isArray(text)) {
    return text.map((t) => (typeof t === "string" ? t : t.text || "")).join("");
  }
  return String(text == null ? "" : text);
}

/** Estimated rendered height in inches, plus the line count behind it. */
function measure(text, o) {
  const size = o.fontSize || 18;
  const face = o.fontFace || "Calibri";
  const adv = (ADVANCE[face] || 0.5) * size / 72;
  const inset = (o.margin === 0 ? 0 : 0.1) * 2;
  const usable = Math.max(0.05, (o.w || 1) - inset);
  const perLine = Math.max(1, Math.floor(usable / adv));
  const lineH = (o.lineSpacing || size * 1.22) / 72;

  let lines = 0;
  plain(text).split("\n").forEach((para) => {
    if (!para.length) { lines += 1; return; }
    let used = 0;
    para.split(/\s+/).forEach((word) => {
      const wLen = word.length + 1;
      if (used && used + wLen > perLine) { lines += 1; used = wLen; }
      else used += wLen;
    });
    lines += 1;
  });
  return { height: lines * lineH, lines, perLine, lineH };
}

module.exports = { measure, plain, ADVANCE };
