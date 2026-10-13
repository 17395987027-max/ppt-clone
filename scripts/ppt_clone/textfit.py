"""CJK-aware text measuring and line breaking for generated slides.

Why this exists
---------------
An SVG ``<text>`` element carries exactly one line — it never wraps. Whoever
emits the slide must therefore decide every line break itself, and the rules
that make Chinese text look right are not the rules a greedy filler produces:

* an opening bracket must not be left dangling at the end of a line;
* closing punctuation (。，、；：！？）…） must not start a line — pull it back
  even if it then hangs slightly past the measure (hanging punctuation);
* the last line must not be a one- or two-character orphan;
* a line whose emitted box is narrower than its glyphs gets re-wrapped by the
  renderer (LibreOffice/WPS) — see ``converter/elements.py``, which floors the
  box width for exactly this reason.

All four are language rules, not deck-specific ones, so they live here instead
of being re-derived in each deck's build script. Widths are in "em units":
1.0 is one full-width CJK glyph.
"""

from __future__ import annotations

# Full-width punctuation that a font may render narrower in advance width but
# must still be measured as a full CJK glyph for line-breaking purposes.
_WIDE_PUNCT = set("·、。，；：（）“”‘’—…《》【】！？")
# A bracket opened at the end of a line, and marks that may not open a line.
_OPEN = "（《“‘【"
_CLOSE = "）》。，、；：！？”’】"


def char_units(ch: str) -> float:
    """Advance width of one character in em units (1.0 = full-width glyph)."""
    if ord(ch) > 0x2E7F or ch in _WIDE_PUNCT:
        return 1.0
    if ch == " ":
        return 0.5
    return 0.55


def text_units(s: str) -> float:
    """Advance width of a whole string in em units."""
    return sum(char_units(c) for c in s)


def units_for_width(px: float, font_size: float, safety: float = 0.82) -> int:
    """How many em units fit in ``px`` at ``font_size``.

    ``safety`` leaves headroom so a renderer never disagrees with the break
    points chosen here (mixed CJK/Latin runs are measured approximately).
    """
    return max(8, int(px / font_size * safety))


def wrap_cjk(s: str, max_units: float, hang: float = 1.5) -> list[str]:
    """Break ``s`` into lines of at most ``max_units`` em units.

    Applies the typographic rules above. ``hang`` is how far a closing mark may
    overhang the measure rather than start the next line.
    """
    lines, cur, u = [], "", 0.0
    for ch in s:
        w = char_units(ch)
        if cur and u + w > max_units:
            lines.append(cur)
            cur, u = "", 0.0
        cur += ch
        u += w
    if cur:
        lines.append(cur)

    # 1. A bracket that opened at the end of a line moves down with the text
    #    it opens, never dangles.
    for i in range(len(lines) - 1):
        if len(lines[i]) > 1 and lines[i][-1] in _OPEN:
            lines[i + 1] = lines[i][-1] + lines[i + 1]
            lines[i] = lines[i][:-1]

    # 2. Closing punctuation is pulled back onto the previous line (two passes
    #    because pulling one mark up can expose another).
    for i in range(len(lines) - 1):
        if (lines[i + 1] and lines[i + 1][0] in _CLOSE
                and text_units(lines[i]) + char_units(lines[i + 1][0]) <= max_units + hang):
            lines[i] += lines[i + 1][0]
            lines[i + 1] = lines[i + 1][1:]

    lines = [ln for ln in lines if ln.strip()]

    # 3. No one- or two-character orphan on the last line.
    if len(lines) >= 2 and len(lines[-1]) <= 2 and len(lines[-2]) > 3:
        take = min(3 - len(lines[-1]), len(lines[-2]) - 1)
        lines[-1] = lines[-2][-take:] + lines[-1]
        lines[-2] = lines[-2][:-take]
    return lines
