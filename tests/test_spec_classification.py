"""Unit tests for page-type and layout-sub-type classification."""

from __future__ import annotations

from ppt_clone.spec.spec_model import Element, ElementType, Pos, SemanticRole
from ppt_clone.spec.enhanced_extractor import (
    _detect_page_type,
    _detect_layout_sub_type,
)


def _txt(x=0.1, y=0.1, w=0.8, h=0.2, text="body", layout=False):
    return Element(element_type=ElementType.TEXT, semantic_role=SemanticRole.BODY,
                   position=Pos(x, y, w, h), text=text, from_layout=layout)


def _img(x=0.0, y=0.0, w=1.0, h=1.0, layout=False):
    return Element(element_type=ElementType.IMAGE, semantic_role=SemanticRole.IMAGE,
                   position=Pos(x, y, w, h), from_layout=layout)


def test_agenda_marked_toc():
    els = [_txt(text="目录"), _txt(text="1"), _txt(text="2"), _txt(text="3")]
    assert _detect_page_type("deck_page_4", 1, 14, els) == "toc"


def test_short_content_page_not_toc():
    # Content page whose bullets are all short must NOT be mistaken for a toc.
    els = [_txt(text="1 业务能力的重要性"),
           _txt(text="规模效应"),
           _txt(text="协同能力"),
           _txt(text="成本方面")]
    assert _detect_page_type("deck_page_1", 2, 14, els) == "content"


def test_last_slide_is_end_page():
    els = [_txt(text="谢谢大家！")]
    assert _detect_page_type("deck_page_1", 13, 14, els) == "end_page"


def test_first_slide_is_cover():
    els = [_txt(text="年度工作总结与未来展望"), _txt(text="主讲：张三")]
    assert _detect_page_type("deck_page_2", 0, 14, els) == "cover"


def test_sub_type_ignores_layout_artwork_and_icons():
    els = [
        _img(0.0, 0.0, 1.0, 1.0, layout=True),   # brand artwork on layout
        _img(0.90, 0.90, 0.03, 0.03),            # tiny logo icon
        _txt(0.05, 0.2, 0.9, 0.3, text="heading"),
        _txt(0.05, 0.5, 0.4, 0.3, text="col a"),
        _txt(0.55, 0.5, 0.4, 0.3, text="col b"),
        _txt(0.05, 0.8, 0.9, 0.1, text="foot"),
    ]
    # No substantial slide image → text-based rule, not "image_right".
    assert _detect_layout_sub_type(els) == "grid"


def test_sub_type_real_photo_left():
    els = [
        _img(0.0, 0.0, 0.5, 1.0),        # half-page photo on the left
        _txt(0.55, 0.2, 0.4, 0.6, text="body"),
    ]
    assert _detect_layout_sub_type(els) == "image_left"
