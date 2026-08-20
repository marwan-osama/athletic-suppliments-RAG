"use strict";
/**
 * Builds the judged deck — nine slides, per the Day 5 brief.
 *
 *   node presentation/build.js
 *
 * The long-form version (27 slides, every measurement and every hurdle) builds
 * from build-appendix.js and is kept for judge questions, not for the talk.
 */

const path = require("path");
const pptxgen = require("pptxgenjs");

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.author = "Team — Evidence-Based Supplement Assistant";
pres.company = "Creativa · Instant · Orange Digital Center";
pres.title = "Evidence-Based Supplement Assistant";
pres.subject = "AI Clinical Decision Support Lite — Hackathon";

require("./build-core")(pres);

const out = path.join(__dirname, "evidence-based-supplement-assistant.pptx");
pres.writeFile({ fileName: out }).then(() => console.log("wrote", out));
