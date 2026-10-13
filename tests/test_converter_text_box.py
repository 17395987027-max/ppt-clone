"""The converted text box must never be narrower than its glyphs.

SVG <text> does not wrap — authors emit one element per line. If the emitted
DrawingML box is narrower than its content, a renderer (LibreOffice/WPS) wraps
it anyway, splitting e.g. a two-digit page number onto two lines.
"""

from __future__ import annotations

import re
from lxml import etree

from ppt_clone.converter.context import ConvertContext
from ppt_clone.converter.elements import convert_text

SVG_NS = "http://www.w3.org/2000/svg"


def _box_width_px(svg: str, font_size: float) -> float:
    ctx = ConvertContext()
    ctx.scale_x = ctx.scale_y = 1.0
    elem = etree.fromstring(svg)
    res = convert_text(elem, ctx)
    assert res is not None
    cx = int(re.search(r'<a:ext cx="(\d+)"', res.xml).group(1))
    return cx / 9525.0  # EMU_PER_PX (96 dpi)


def test_narrow_digits_box_not_underestimated():
    # A bold two-digit label at 12px — the exact case that wrapped in previews.
    for txt in ("11", "08", "2026"):
        w = _box_width_px(
            f'<text xmlns="{SVG_NS}" x="40" y="692" font-size="12" '
            f'font-weight="bold">{txt}</text>', 12)
        assert w >= len(txt) * 12 * 0.75, f"{txt!r} box too narrow: {w}"


def test_cjk_box_generous():
    w = _box_width_px(
        f'<text xmlns="{SVG_NS}" x="0" y="0" font-size="20">服务体系</text>', 20)
    assert w >= 4 * 20 * 0.9
