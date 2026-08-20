"use strict";
/**
 * Shared visual kit for the deck: palette, type scale, and the handful of
 * primitives every slide is built from.
 *
 * The motif is a numbered chip plus a monospace citation — the two things the
 * system itself is about (an ordered pipeline, and a page you can check).
 */

const fs = require("fs");
const path = require("path");
const { measure } = require("./metrics");

// --- palette --------------------------------------------------------------- //
// Ink dominates; orange is the single sharp accent and ties to Orange Digital
// Center; green/red are reserved for measured pass/fail and never decoration.
const C = {
  ink: "0E1A2B",
  inkSoft: "17293E",
  inkLine: "2A3D55",
  paper: "FFFFFF",
  tint: "F1F4F8",
  tintDeep: "E3E9F1",
  orange: "FF7900",
  green: "0E7C5A",
  red: "B3261E",
  amber: "B26A00",
  mute: "6B7A8C",
  muteDark: "8FA3B8",
  rule: "D8DEE6",
};

const F = {
  head: "Cambria",   // journal-ish: this is a deck about published evidence
  body: "Calibri",
  mono: "Courier New", // system output, chunk ids, citations
};

const W = 13.333;
const H = 7.5;
const M = 0.62;          // slide margin
const FOOT = H - 0.52;   // logo baseline

// --- logos ----------------------------------------------------------------- //
const LOGO_DIR = path.join(__dirname, "..", "assets", "logos");
const ORGS = [
  { key: "creativa", label: "CREATIVA", tint: "1B6FD1" },
  { key: "instant", label: "INSTANT", tint: "12856B" },
  { key: "orange", label: "ORANGE DIGITAL CENTER", tint: C.orange, wide: true },
];

/**
 * A logo file for `key`, preferring the variant that suits the background.
 * `name-light.png` is used on dark slides, `name.png` otherwise — a navy
 * wordmark on an ink background is invisible, which is the whole reason the
 * light variants exist.
 */
function logoFile(key, dark) {
  if (!fs.existsSync(LOGO_DIR)) return null;
  const files = fs.readdirSync(LOGO_DIR).filter((f) => /\.(png|jpe?g)$/i.test(f));
  const forKey = files.filter((f) => f.toLowerCase().includes(key));
  const light = forKey.find((f) => /-light\./i.test(f));
  const plain = forKey.find((f) => !/-light\./i.test(f));
  const pick = dark ? light || plain : plain || light;
  return pick ? path.join(LOGO_DIR, pick) : null;
}

/** PNG pixel dimensions, straight from the IHDR chunk — no image library. */
function pngSize(file) {
  try {
    const fd = fs.openSync(file, "r");
    const head = Buffer.alloc(24);
    fs.readSync(fd, head, 0, 24, 0);
    fs.closeSync(fd);
    if (head.toString("ascii", 1, 4) !== "PNG") return null;
    return { w: head.readUInt32BE(16), h: head.readUInt32BE(20) };
  } catch {
    return null;
  }
}

// The three marks have very different proportions — Creativa is nearly square,
// Instant is a wordmark almost eight times as wide as it is tall. Each is
// fitted inside this box rather than forced to a common width, so none is
// distorted and none shrinks to nothing.
const LOGO_BOX = { w: 1.62, h: 0.42 };

/**
 * Organiser logos, on every slide.
 *
 * A real file is used wherever one exists; anything missing falls back to a
 * typographic wordmark — deliberately a wordmark rather than an invented mark,
 * so it can never misrepresent the logo it stands in for.
 *
 * On dark slides the row sits on a white plate. Creativa's mark is dark blue
 * and multi-coloured: recolouring it to suit a dark background would
 * misrepresent it, so the background changes instead of the logo.
 */
function logos(slide, dark) {
  // Always the plain artwork: on dark slides it sits on the white plate below,
  // so the light variants would be white-on-white. They stay in the folder for
  // anyone who wants a plateless treatment.
  const placed = ORGS.map((o) => {
    const file = logoFile(o.key, false);
    const size = file ? pngSize(file) : null;
    if (!file || !size) {
      return { ...o, file: null, w: o.label.length * 0.072 + 0.14, h: 0.3 };
    }
    const scale = Math.min(LOGO_BOX.w / size.w, LOGO_BOX.h / size.h);
    return { ...o, file, w: size.w * scale, h: size.h * scale };
  });

  const GAP = 0.36;
  const total = placed.reduce((sum, p) => sum + p.w, 0) + GAP * (placed.length - 1);
  const mid = FOOT + 0.02;

  const PAD = 0.18;
  if (dark) {
    slide.addShape("roundRect", {
      x: M, y: mid - LOGO_BOX.h / 2 - 0.11,
      w: total + PAD * 2, h: LOGO_BOX.h + 0.22, rectRadius: 0.06,
      fill: { color: C.paper }, line: { color: C.paper },
      isFooter: true,
    });
  }

  let x = dark ? M + PAD : M;
  placed.forEach((p) => {
    if (p.file) {
      slide.addImage({
        path: p.file, x, y: mid - p.h / 2, w: p.w, h: p.h,
        isFooter: true, // audit: the footer is where these belong
      });
    } else {
      slide.addText(p.label, {
        x, y: mid - 0.15, w: p.w, h: 0.3, margin: 0,
        fontFace: F.body, fontSize: 8.5, bold: true, charSpacing: 1.0,
        color: C.ink, valign: "middle", isFooter: true,
      });
    }
    x += p.w + GAP;
  });
}

// --- backgrounds ----------------------------------------------------------- //
function dark(slide) {
  slide.background = { color: C.ink };
  logos(slide, true);
}

function light(slide) {
  slide.background = { color: C.paper };
  logos(slide, false);
}

// --- text primitives ------------------------------------------------------- //
/**
 * Kicker + title block. Returns the y the body should start at.
 *
 * The box is sized from the measured line count rather than a fixed height, so
 * a title that wraps pushes its slide's content down instead of overprinting
 * it — every caller lays out from the returned y.
 */
function title(slide, kicker, text, opts = {}) {
  const d = !!opts.dark;
  const y = opts.y === undefined ? M - 0.06 : opts.y;
  const size = opts.size || 30;
  const w = opts.w || W - M * 2;
  const lineSpacing = opts.size ? opts.size * 1.1 : 33;
  if (kicker) {
    slide.addText(kicker.toUpperCase(), {
      x: M, y, w: W - M * 2, h: 0.26, margin: 0,
      fontFace: F.body, fontSize: 10.5, bold: true, charSpacing: 1.4,
      color: C.orange,
    });
  }
  const box = { fontFace: F.head, fontSize: size, w, margin: 0, lineSpacing };
  const h = opts.h || Math.max(0.62, measure(text, box).height + 0.06);
  slide.addText(text, Object.assign({}, box, {
    x: M, y: y + (kicker ? 0.28 : 0), h,
    bold: true, color: d ? C.paper : C.ink, valign: "top",
  }));
  return y + (kicker ? 0.28 : 0) + h + (opts.gap === undefined ? 0.2 : opts.gap);
}

/**
 * Standfirst under a title. Sized to its content, like `title`.
 *
 * `y` comes second, ahead of the text, so a call cannot silently lose it in a
 * wrapped multi-line string — which is exactly how four slides ended up writing
 * this shape at y=0 and piling themselves against the top of the page.
 * pptxgenjs takes undefined as zero, and every audit comparison is false
 * against undefined, so nothing caught it short of looking at a render.
 */
function lede(slide, y, text, opts = {}) {
  if (!Number.isFinite(y)) {
    throw new Error(`lede() needs a numeric y (got ${y}) for: ${String(text).slice(0, 60)}`);
  }
  const d = !!opts.dark;
  const box = {
    fontFace: F.body, fontSize: opts.size || 14.5,
    w: opts.w || W - M * 2, margin: 0, lineSpacing: 20,
  };
  const h = opts.h || measure(text, box).height + 0.06;
  slide.addText(text, Object.assign({}, box, {
    x: M, y, h, italic: opts.italic !== false,
    color: d ? C.muteDark : C.mute, valign: "top",
  }));
  return y + h + 0.16;
}

/** A soft card. No edge stripes — tint and shadow only. */
function card(slide, o) {
  slide.addShape("roundRect", {
    x: o.x, y: o.y, w: o.w, h: o.h, rectRadius: 0.06,
    fill: { color: o.fill || (o.dark ? C.inkSoft : C.tint) },
    line: { color: o.line || (o.dark ? C.inkLine : C.tintDeep), width: 0.75 },
    shadow: o.flat ? undefined : {
      type: "outer", angle: 90, blur: 10, offset: 0.04,
      color: "000000", opacity: o.dark ? 0.35 : 0.09,
    },
  });
}

/** Numbered circular chip — the repeating motif. */
function chip(slide, n, x, y, o = {}) {
  const d = o.diam || 0.36;
  slide.addShape("ellipse", {
    x, y, w: d, h: d,
    fill: { color: o.fill || C.orange }, line: { color: o.fill || C.orange },
  });
  slide.addText(String(n), {
    x, y, w: d, h: d, margin: 0, align: "center", valign: "middle",
    fontFace: F.body, fontSize: o.size || 13, bold: true, color: o.color || C.paper,
  });
}

/** Big number + label, for stat rows. */
function stat(slide, o) {
  slide.addText(o.value, {
    x: o.x, y: o.y, w: o.w, h: o.vh || 0.72, margin: 0,
    fontFace: F.head, fontSize: o.size || 40, bold: true,
    color: o.color || C.ink, valign: "middle", align: o.align || "left",
  });
  const lbl = {
    fontFace: F.body, fontSize: o.labelSize || 11, w: o.w, margin: 0, lineSpacing: 14,
  };
  slide.addText(o.label, Object.assign({}, lbl, {
    x: o.x, y: o.y + (o.vh || 0.72),
    h: o.lh || Math.max(0.3, measure(o.label, lbl).height),
    color: o.labelColor || C.mute, valign: "top", align: o.align || "left",
  }));
}

/** Monospace block for system output / code. */
function mono(slide, text, o) {
  card(slide, { x: o.x, y: o.y, w: o.w, h: o.h, dark: true, fill: o.fill || C.ink, line: o.line || C.inkLine, flat: o.flat });
  slide.addText(text, {
    x: o.x + 0.18, y: o.y + 0.13, w: o.w - 0.36, h: o.h - 0.26, margin: 0,
    fontFace: F.mono, fontSize: o.size || 10, color: o.color || "C9D6E4",
    valign: "top", lineSpacing: o.lineSpacing || 14,
  });
}

/** Small pill label, e.g. PASS / FAIL / status. */
function pill(slide, text, o) {
  const w = o.w || 0.2 + text.length * 0.072;
  slide.addShape("roundRect", {
    x: o.x, y: o.y, w, h: o.h || 0.24, rectRadius: 0.12,
    fill: { color: o.fill || C.green }, line: { color: o.fill || C.green },
  });
  slide.addText(text, {
    x: o.x, y: o.y, w, h: o.h || 0.24, margin: 0, align: "center", valign: "middle",
    fontFace: F.body, fontSize: o.size || 8.5, bold: true, charSpacing: 0.5,
    color: o.color || C.paper,
  });
  return w;
}

/** Section divider. */
function divider(slide, num, kicker, text, note) {
  dark(slide);
  slide.addText(num, {
    x: M, y: 1.86, w: 2.2, h: 2.14, margin: 0,
    fontFace: F.head, fontSize: 116, bold: true, color: C.inkLine, valign: "middle",
  });
  slide.addText(kicker.toUpperCase(), {
    x: M + 2.05, y: 2.14, w: W - M * 2 - 2.05, h: 0.3, margin: 0,
    fontFace: F.body, fontSize: 11, bold: true, charSpacing: 1.6, color: C.orange,
  });
  slide.addText(text, {
    x: M + 2.02, y: 2.44, w: W - M * 2 - 2.2, h: 1.1, margin: 0,
    fontFace: F.head, fontSize: 34, bold: true, color: C.paper, valign: "top",
    lineSpacing: 40,
  });
  if (note) {
    slide.addText(note, {
      x: M + 2.05, y: 3.76, w: W - M * 2 - 2.6, h: 0.8, margin: 0,
      fontFace: F.body, fontSize: 13.5, italic: true, color: C.muteDark,
      valign: "top", lineSpacing: 19,
    });
  }
}

/** Shared chart frame options — quiet axes, palette colours, no dated default. */
function chartFrame(extra = {}) {
  return Object.assign({
    showTitle: false,
    showLegend: false,
    catAxisLabelColor: C.mute,
    valAxisLabelColor: C.mute,
    catAxisLabelFontFace: F.body,
    valAxisLabelFontFace: F.body,
    catAxisLabelFontSize: 10.5,
    valAxisLabelFontSize: 9.5,
    catGridLine: { style: "none" },
    valGridLine: { color: C.rule, size: 0.5 },
    catAxisLineShow: false,
    valAxisLineShow: false,
    dataLabelFontFace: F.body,
    dataLabelFontSize: 9.5,
    dataLabelFontBold: true,
  }, extra);
}

module.exports = { C, F, W, H, M, FOOT, dark, light, title, lede, card, chip, stat, mono, pill, divider, chartFrame, logoFile };
