# The hackathon deck

`evidence-based-supplement-assistant.pptx` — 26 slides, built from source rather
than edited by hand, so a corrected figure is a one-line change and a rebuild.

```bash
node presentation/build.js      # writes the .pptx
node presentation/audit.js      # geometry check — run before shipping
```

## Layout

| File | Holds |
| --- | --- |
| [build.js](build.js) | entry point: page size, metadata, output path |
| [build-part1.js](build-part1.js) | slides 1-13 — problem, solution, technology, need |
| [build-part2.js](build-part2.js) | slides 14-26 — the technical work, results, hurdles |
| [lib/kit.js](lib/kit.js) | palette, type scale, and every drawing primitive |
| [lib/metrics.js](lib/metrics.js) | text-fit arithmetic, shared with the audit |
| [audit.js](audit.js) | geometry check (see below) |

## Assets

Both folders are read at build time and the deck degrades gracefully when they
are empty, so it always builds:

```
assets/logos/     creativa.png, instant.png, orange.png   → footer of every slide
assets/screens/   any .png/.jpg                            → the product slide
```

Logo files are matched by **substring of the filename**, so `orange-digital-
center.png` is found for `orange`. `.png` and `.jpg` both work. With no files
present the footer draws wordmark stand-ins at the same size and position, so
dropping the real files in changes nothing else on the slide.

## The audit

There is no PowerPoint here to look at the slides in, so the geometry is checked
arithmetically instead. `audit.js` wraps the pptxgenjs API, records every box the
deck draws, and reports:

- **ESCAPES** — text that will render taller than the card framing it. PowerPoint
  does not clip an overfull text box, it spills, so this is the check that
  matters rather than "text bigger than its box".
- **COLLIDE** — text landing on the block beneath it, within the same column.
- **MARGIN / FOOTER / OFFSLIDE** — anything crossing the 0.62" margin, running
  into the logo footer, or leaving the slide.

Line counts come from average character advances per font family, so they are
estimates — accurate enough to catch a real overrun, not a substitute for
looking at the rendered slides. `title()`, `lede()`, `beats()` and `stat()` size
themselves from the same arithmetic, which is why adding a sentence pushes the
rest of a slide down instead of printing on top of it.

## Rendering

```bash
soffice --headless --convert-to pdf evidence-based-supplement-assistant.pptx
pdftoppm -jpeg -r 150 evidence-based-supplement-assistant.pdf slide
```

## Where the numbers come from

Every figure on a slide is traceable to something checked in:

| Slide | Source |
| --- | --- |
| extraction, chunking, page coverage | [docs/engineering-log.md](../docs/engineering-log.md) §3.2-3.3 |
| prompt-fix before/after | `eval_results/eval_report_20260820_010736.json` → `..._020829.json` |
| depth, and the shipped configuration | `eval_results/eval_report_20260820_033634.json` |
| the need statistics | the indexed corpus itself, pages 1-2 |
| test counts | `tests/test_pipeline.py`, `tests/test_evaluation.py` |

Two reports must **not** be quoted — `eval_report_20260820_013754.json` and
`eval_report_20260820_045034.json` are runs whose judge failed part way through.
Their answers are valid; their scores are not. See `H13` and `H18` in the log.
