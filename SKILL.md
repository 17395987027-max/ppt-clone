---
name: ppt-clone
description: Replicate a reference PowerPoint deck. Extract the design spec (palette, fonts, per-page layout geometry, reusable assets) from an existing .pptx, then generate new slides in that same style and export them as natively editable shapes. Use when the user asks to copy or replicate a PPT template / style, to extract a design spec from a pptx, or to make slides that match a reference deck.
---

# ppt-clone — read a template, replicate it

One loop, in three steps:

```
reference.pptx  ──extract-spec──▶  specs/<name>/  ──generate-pptx──▶  .svg  ──convert──▶  .pptx
   (design DNA)                      (the spec)                       (slides)          (native shapes)
```

Nothing else: the skill reads a deck you like and produces a new deck in the
same visual language, as real PowerPoint shapes (text stays editable).

## Environment (this machine)

System `python3` is 3.9 and too old; dependencies live in the project venv.
Run every command from the skill root:

```bash
cd ~/.claude/skills/ppt-clone
./.venv/bin/python scripts/ppt_cli.py <command>
```

LibreOffice renders previews (`/Applications/LibreOffice.app/Contents/MacOS/soffice`,
also on PATH as `soffice`); `pdftoppm` is on PATH.

## Commands

| Command | What it does |
|---------|--------------|
| `extract-spec <ref.pptx> [--name X]` | Read the reference deck → `specs/<name>/` (`spec.yaml`, `pages/`, `assets/`) |
| `generate-pptx --spec specs/X --outline outline.yaml -o out.pptx [--workers 4]` | Generate slides against the spec with the agent loop, then export |
| `convert <svg>... -o out.pptx` | SVG → native-shape PPTX |
| `list-specs` / `select-spec <name>` | The extracted specs / mark one active |
| `qa-balance <png-dir> --box L,T,R,B [--deck-width W]` | Per-page whitespace balance from renders (flags top-heavy or over-sparse pages) |

## Workflow

### 1. Extract the spec

```bash
./.venv/bin/python scripts/ppt_cli.py extract-spec template.pptx --name house
```

Reads the reference with `python-pptx` **including the slide layout**, where a
branded deck keeps its background artwork, divider rules and logo
(`slide.shapes` alone loses them). Writes:

```
specs/house/
├── spec.yaml        palette (real HEX), fonts, canvas, per-page index
├── pages/           one YAML per page: elements, positions, styles, text
├── assets/          extracted backgrounds / logos / decoration
└── logic.yaml       narrative + density rhythm
```

Then sanity-check it — [references/lessons-learned.md](references/lessons-learned.md) §1.8
(does every page carry its background? are colours non-blank? does the agenda
classify as `toc`? does every page YAML load?).

### 2. Generate against the spec

Give the outline YAML (`slides: [{title, body: [...]}]`) and run
`generate-pptx`. Per slide the agent loop generates SVG, scores it against the
spec (colour 30% / layout 30% / typography 20% / background 15% / density 5%)
and regenerates on anything under 90%, up to 5 rounds.

Layout rules to apply while writing the SVG are in
[references/prompt-ppt-layout.md](references/prompt-ppt-layout.md) — hierarchy
(W/P/S), one primary colour, 1.5× line spacing, no text touching an edge,
§4.4 vertical balance, §7.8 body-layout patterns.
Break CJK lines with `ppt_clone.textfit.wrap_cjk` and emit **one `<text>`
element per line** (SVG text never wraps).

### 3. Convert

```bash
./.venv/bin/python scripts/ppt_cli.py convert build/*.svg -o out.pptx
```

Write the SVGs into a fresh directory: a stale SVG from an earlier build joins
the output silently (`convert` warns about siblings it is ignoring).

### 4. Verify

Render and measure, rather than trusting the arithmetic:

```bash
soffice --headless --convert-to pdf --outdir build/render out.pptx
pdftoppm -r 90 -png build/render/out.pdf build/render/p
./.venv/bin/python scripts/ppt_cli.py qa-balance build/render/p* 2>/dev/null \
    --box <L>,<T>,<R>,<B> --deck-width <deck width>
```

`--box` is the content band in the deck's own points, excluding the header band
and the footer row (include them and every page measures "full"). Then build a
contact sheet and look at it; some defects only show at that scale.

## Pitfalls

[references/lessons-learned.md](references/lessons-learned.md) is the field
notes: layout-level artwork missing from the spec, scheme colours resolving
blank, tints/alpha/gradients python-pptx hides, text boxes re-wrapping in
LibreOffice, stale SVGs, CJK line-breaking and vertical-balance rules, and how
to verify. **Skim it before the first real deck** — each entry is symptom →
cause → fix.

Three helpers came out of that work and are used by the layouts:

| Module | Purpose |
|--------|---------|
| `scripts/ppt_clone/textfit.py` | CJK width model + `wrap_cjk()` (no dangling brackets, no punctuation opening a line, no orphans) |
| `scripts/ppt_clone/layout_fit.py` | `fit_block()` — largest size that fits a band, capped gap growth, then centring |
| `scripts/ppt_clone/layout_qa.py` | Ink-bounding-box balance check over rendered pages |

## Resources

| Path | Contents |
|------|----------|
| `scripts/ppt_cli.py` | The CLI |
| `scripts/ppt_clone/spec/` | Spec extraction (theme, elements, assets, classification) |
| `scripts/ppt_clone/converter/`, `finalize/` | SVG → DrawingML |
| `scripts/ppt_clone/{ppt_generator,slide_generator,style_evaluator}.py` | Generation + scoring loop |
| `references/spec-format.md`, `prompt-ppt-layout.md`, `lessons-learned.md` | Spec schema, layout rules, field notes |
| `tests/` | Unit tests (`./.venv/bin/python -m pytest tests -q`) |

## Requirements

Python 3.10+, `python-pptx`, `Pillow`, `PyYAML`, `lxml`, `pdf2image`
(see `requirements.txt`). LibreOffice + poppler for rendering previews.
