# Lessons learned building a real deck

Provenance: written after building a long Chinese deck in a branded house style,
generated from a content model and matched to an existing `.pptx` used as the
design reference. Every item below was an *observed* defect on that job — with a
reproduction — not a theory. Deck-specific and client-specific details are
deliberately excluded; only lessons that generalise to the next deck are kept.
Extraction items 1.1–1.7 are already fixed in the code and covered by tests; the
notes say where.

---

## 1. Extracting a spec from a branded reference deck

### 1.1 The deck's artwork lives on the slide LAYOUT, not the slide
`slide.shapes` only returns shapes owned by the slide. In a real branded deck the
background painting, the dimming overlay, the divider rules and the logo sit on
the **slide layout**, so a spec built from `slide.shapes` alone loses the entire
background and reports every page as plain white.
Fix: iterate `slide.slide_layout.shapes` first (skipping placeholders), mark the
elements `from_layout=True`, and share one z-order counter
(`spec/enhanced_extractor.py`).

### 1.2 Element classification must ignore layout-inherited shapes
The same shared artwork skews page classification: a full-bleed layout picture
made ordinary text pages classify as `image_right`, and the footer logo flipped
others. Always filter `from_layout` (and shapes under ~5% of the slide area)
before classifying. `tests/test_spec_classification.py` pins this.

### 1.3 Page type detection: require an explicit marker, not a shape heuristic
"Many short lines near the front" labelled a normal content page as `toc` while
missing the real agenda (whose items are single characters `1 2 3 4`). Require a
marker word (目录 / agenda / contents) **and** a short page. Never infer the
page type from bullet length alone.

### 1.4 Colours: resolve scheme colours to HEX before writing the spec
Branded decks colour almost everything with theme/scheme references
(`accent1`, `dk1`, `tx1`, `bg1`). `ColorFormat.rgb` raises on those, and if each
call site swallows the error the spec ends up with **blank** fill/stroke/font
colours (on the reference deck: 51/60 shapes without fill, 48/65 texts without
colour). Seed the theme palette once (`set_theme_colors(extract_theme_colors(…))`)
and resolve `srgb → hex`, `scheme → palette`, remembering the `tx1/bg1 → dk1/lt1`
aliasing.

### 1.5 Tints, shades and gradients are invisible to python-pptx
A line stored as "accent1 lightened 40%" reads as plain accent1 through
`ColorFormat`, so dividers come out the wrong colour. Read the raw colour element
and apply `lumMod`/`lumOff`/`tint`/`shade` in HSL; likewise read gradient stops
and angle from the XML. Related: don't `return` early when a shape has no `.fill`
(connectors) — that skips line extraction entirely and loses every connector.

### 1.6 Alpha is a separate child element
`<a:alpha>` on a fill is not exposed by python-pptx; a 20% dimming overlay was
recorded as an opaque block. Parse it into `fill_opacity` / `stroke_opacity`.

### 1.7 Two small data-integrity traps
* `extract --name X` must pass `X` down so **assets and pages land in the same
  directory** (otherwise pages go to `specs/X/` and assets to `specs/<stem>/`).
* `paragraph.line_spacing` can be a `Length` (exact spacing), not a float
  multiple. Assigning it straight onto a float field emits
  `!!python/object/new:pptx.util.Centipoints` into the YAML, which
  `yaml.safe_load` then rejects — and the generator's `try/except` silently drops
  the page.

### 1.8 Checklist before trusting a new reference spec
1. Does every page carry its background image / band?
2. Are fill/stroke/font colours non-blank wherever the reference has a solid
   colour?
3. Does the agenda classify as `toc`, and a random content page as `content`?
4. Does every page YAML load with `yaml.safe_load`?

---

## 2. SVG → native PPTX conversion

### 2.1 `<text>` never wraps — one element per line
There is no line breaking in SVG text. The generator owns every break, so it
needs a CJK-aware wrapper. `scripts/ppt_clone/textfit.py` implements the rules
that a naive greedy fill gets wrong:
* an opening bracket (`（《“‘【`) must never end a line;
* closing punctuation (`）》。，、；：！？”’】`) must never start a line — pull it
  back even if it then hangs past the measure;
* no one-or-two-character orphan on the last line;
* measure in em units (`char_units`: CJK ≈ 1.0, Latin ≈ 0.55, space ≈ 0.5), with
  a ~0.82 safety factor so the renderer agrees with the chosen breaks.

### 2.2 The emitted text box must be at least as wide as its glyphs
`estimate_text_width` underestimates narrow glyphs (`"1"` ≈ 0.3em) and mixed
CJK/Latin runs. When the DrawingML box is narrower than its content, LibreOffice
and WPS **re-wrap it**: a two-digit page number rendered as two stacked lines
(`1` over `1`), and card text like `会议谈判` broke in half. Fix (in
`converter/elements.py`): floor the box at `len(text) * font_size * 0.75`, use
`estimate * 1.25`, and pad by `font_size * 0.15`.
Regression test: `tests/test_converter_text_box.py`. Symptom to recognise in a
preview: text that *looks* auto-wrapped, or a lone character on its own line,
means the box is too narrow — not that the font is wrong.

### 2.3 Stale SVGs from a previous run silently join the deck
Slides left over from an earlier, longer build (e.g. `slide_25..34`, still
carrying stale text from the superseded version) get converted into the new PPTX when the SVGs are
passed as a directory or glob. Generate into a fresh directory, or overwrite
every file with its final content. `ppt_cli.py convert` now warns when sibling
`.svg` files in the same directory are not part of the conversion. Verify the
deliverable by extracting all text and grepping for strings that must not
appear.

---

## 3. Laying out a CJK page

### 3.1 Auto-fit: pick the largest size that fits, then spend the slack
A fixed font size plus top-aligned content is the most common cause of
"content crowded at the top, empty at the bottom". Use a descending size ladder
(15→22pt) and take the first that fits the content band; then distribute the
leftover height into the inter-row gaps (capped at ~1× the base gap) and centre
the block in the band. Long lists settle on a small size and fill; short lists
use a large size and stay centred.

This arithmetic is now a module — `ppt_clone.layout_fit.fit_block()` — because
re-deriving it per layout is how the first two attempts went wrong (no
distribution at all → crowding; unbounded growth → gaps that look broken).
Contract worth knowing: if the content cannot fit even at the smallest size,
it returns the smallest size with offset 0; the caller must shorten the text or
split the page, and `qa-balance` will flag the page. See also
[prompt-ppt-layout.md](prompt-ppt-layout.md) §4.4 and §7.8 for the rules and the
body-layout patterns they came from.

### 3.2 Panels and cards: centre the grid, scale the type with the panel
* Centre the whole grid in the band — a short grid otherwise hugs the top edge.
* A lone row of cards must not stretch to full height (cap it, ~300pt).
* Size the heading/body **from the panel height**: a 3-row card grid gives each
  card ~115pt, which cannot hold a 22pt heading plus two 16pt lines without the
  last line crossing the panel border. Scale down (e.g. 18/14 for shallow cards).

### 3.3 A footnote bar must be commensurate with its own text
A full-width tinted bar holding two ragged, left-aligned lines reads as broken:
the box is far wider than the text and the second line ends early. Either balance
the two lines, or — better — make the note a **peer panel aligned with the column
above it** instead of a full-width bar. Prefer restructuring over recolouring;
the defect is geometric, not chromatic.

### 3.4 Two-column pages: align the blocks' vertical extents
When a diagram sits beside a stack of panels, centre the diagram against the
stack (same midpoint) and scale it to a similar height. A small diagram next to a
tall column looks lost.

---

## 4. Verification loop

### 4.1 Render → measure → contact sheet
Arithmetic can be self-consistent and still wrong on the slide. Render with
`soffice --headless --convert-to pdf` + `pdftoppm -r 90 -png`, then measure the
ink bounding box of every page inside its content band:

```bash
./.venv/bin/python scripts/ppt_cli.py qa-balance build/render \
    --box <L>,<T>,<R>,<B> --deck-width <deck width> --max-gap 70
```

`--box` excludes the header band and the footer logo/page-number row — include
them and every page measures "full". A page whose top and bottom margins differ
by more than ~10px is off-centre; a margin above ~70px means the content is
genuinely too sparse for the box. Build a 4×6 contact sheet with PIL and read it
as an image before shipping; some defects (a hollow panel, a note bar wider than
its text) are only obvious at that scale.

### 4.2 Re-read the deliverable, not the source
Open the final `.pptx` and assert the things that matter: slide count, no
template leftovers, expected names/titles present. The SVG sources and the PPTX
can disagree (see 2.3).

---

## 5. Reusing material found in a source PDF

* Prefer vector structure over pixels: `pdftocairo -svg` gives the real paths and
  fills of a diagram; `pdftotext -bbox` gives per-word coordinates; PIL colour
  sampling gives the palette. PyMuPDF (`fitz`) is **not** installed on this
  machine — don't plan around it.
* Reuse the *idea*, not the pixels, when the source is off-palette, carries
  another organisation's branding, or is marked internal/confidential — a
  footer notice telling the reader not to distribute the file, or a licence
  restricting it to internal/trial use, both mean no. Rebuild the structure in
  the deck's own palette and typography — that also fixes the resolution and
  the aspect ratio.
* Say so when nothing fits. Forcing an irrelevant image in is worse than a page
  of type.

---

---

## 6. Programmatic decks (a second, sometimes better path)

When a deck is long, has a house style, and gets restructured more than once,
generating it with a script beats prompting per page: a content model (one entry
per slide) plus a small library of body layouts (labelled rows, card grid,
numbered columns, timeline, figure + panels) makes a restructure a data edit
rather than a re-generation. That is how one long deck survived two structural
rewrites and a dozen balance fixes here.

Keep the two halves apart — content in the model, geometry in the layouts — and
let both use the shared modules: `textfit.wrap_cjk` for line breaking,
`layout_fit.fit_block` for vertical fit, `layout_qa` for acceptance. This path is
**not** wired into the skill's own pipeline (which is agent-per-page SVG
generation); treat it as a pattern to reuse, not a command to call.

---

## 7. Environment gotchas (this machine)

* Run everything with the project venv: `./.venv/bin/python` (system `python3` is
  3.9 and lacks the dependencies). Set `PYTHONPATH=scripts` when importing
  `ppt_clone` from elsewhere.
* LibreOffice at `/Applications/LibreOffice.app/Contents/MacOS/soffice` is on
  PATH as `soffice`; the first headless conversion of a session is slow (up to a
  minute) — don't kill it.
* Fonts: the deck and the renderer must agree. A font present in the `.pptx` but
  missing at render time changes metrics, which shows up as re-wrapped text.
* Deletion may be unavailable (a sandbox can deny `rm`). Build steps should
  overwrite or write into a fresh directory rather than depend on cleaning up —
  which is also what §2.3 asks for.
