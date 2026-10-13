"""Line breaking rules for CJK text emitted as one SVG <text> per line."""

from __future__ import annotations

from ppt_clone.textfit import char_units, text_units, units_for_width, wrap_cjk

MEASURE = 18  # em units per line


def test_full_width_glyphs_measure_one_unit():
    assert char_units("字") == 1.0
    assert char_units("，") == 1.0
    assert char_units("A") == 0.55
    assert char_units(" ") == 0.5


def test_latin_run_is_not_counted_as_full_width():
    assert text_units("AI") < text_units("应用")


def test_units_for_width_keeps_safety_margin():
    # 640px at 16px => 40 glyphs, and the 0.82 safety factor reserves headroom.
    assert 8 <= units_for_width(640, 16) < 40


def test_lines_never_end_with_an_opening_bracket():
    # A naive greedy fill breaks right after "（", stranding the bracket.
    text = "需求调研、方案设计、开发实施与交付（含培训与运维支持）、通用工具平台"
    for ln in wrap_cjk(text, MEASURE):
        assert not ln.endswith(tuple("（《“‘【")), ln


def test_closing_punctuation_never_starts_a_line_and_may_hang():
    # A greedy fill puts "：" at the head of the last line; it must be pulled
    # back onto the previous line even though it then overhangs the measure
    # (hanging punctuation).
    lines = wrap_cjk("资料收集、方案讨论、需求确认、文档编写、审核定稿：2-3 个工作日内回复", 12)
    assert all(ln[0] not in "）》。，、；：！？”’】" for ln in lines), lines


def test_no_single_character_orphan_on_last_line():
    # A greedy fill leaves "区" alone on the last line.
    lines = wrap_cjk("甲园区、乙社区、丙片区、丁园区、戊社区", MEASURE)
    assert len(lines[-1]) >= 2, lines


def test_short_text_is_one_line():
    assert wrap_cjk("简明摘要", MEASURE) == ["简明摘要"]


def test_every_line_respects_the_measure_apart_from_hanging_marks():
    text = "以《系统使用规范》《生成内容标注要求》明确使用边界，生成内容一律经人工审核把关"
    for ln in wrap_cjk(text, MEASURE):
        over = text_units(ln) - MEASURE
        assert over <= 1.5 or not ln[-1] in "）》。，、；：！？”’】", (ln, over)
