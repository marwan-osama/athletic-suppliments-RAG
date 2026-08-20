"use strict";
/**
 * The long deck — every measurement, every hurdle, in full.
 *
 *   node presentation/build-appendix.js
 *
 * Not the talk. This is what you open when a judge asks "where did that number
 * come from" or "what went wrong", and it is the record the core deck's
 * percentages are drawn from.
 */

const path = require("path");
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "Team — Evidence-Based Supplement Assistant";
pres.company = "Creativa · Instant · Orange Digital Center";
pres.title = "Supplement Assistant — Technical Appendix";

require("./build-part1")(pres);
require("./build-part2")(pres);

const out = path.join(__dirname, "supplement-assistant-appendix.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("wrote", out));
