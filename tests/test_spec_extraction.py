"""The extraction path: a reference .pptx -> specs/<name>/ (spec.yaml + pages/)."""

from __future__ import annotations

import pytest
import yaml
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.util import Inches, Pt

from ppt_clone.cli.spec_commands import get_active_spec, list_specs, select_spec
from ppt_clone.spec.enhanced_extractor import SpecExtractor


@pytest.fixture
def reference(tmp_path):
    """A tiny deck with a branded band, a cover title and an agenda page."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    cover = prs.slides.add_slide(prs.slide_layouts[6])
    band = cover.shapes.add_shape(1, Inches(0), Inches(0), Inches(13.333), Inches(2))
    band.fill.solid()
    band.fill.fore_color.rgb = RGBColor(0x7E, 0x69, 0x4F)
    title = cover.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(11), Inches(1))
    title.text_frame.text = "示例参考稿封面"
    title.text_frame.paragraphs[0].runs[0].font.size = Pt(40)

    agenda = prs.slides.add_slide(prs.slide_layouts[6])
    agenda.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(5), Inches(0.8)) \
        .text_frame.text = "目录"
    for i in (1, 2, 3):
        agenda.shapes.add_textbox(Inches(0.8), Inches(1.6 + i * 0.6), Inches(5), Inches(0.5)) \
            .text_frame.text = f"{i} 章节"

    path = tmp_path / "reference.pptx"
    prs.save(path)
    return path


def _extract(tmp_path, reference, name="ref"):
    extractor = SpecExtractor()
    spec = extractor.extract(reference, name=name)
    extractor.save(spec)
    return spec


def test_extracts_palette_and_pages(reference, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = _extract(tmp_path, reference)

    assert spec.metadata["name"] == "ref"
    palette = spec.palette.to_dict()
    assert palette and not any(v is None for v in palette.values())
    assert spec.pages
    assert "toc" in spec.page_types_found


def test_writes_the_spec_directory(reference, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _extract(tmp_path, reference)

    spec_dir = tmp_path / "specs" / "ref"
    assert (spec_dir / "spec.yaml").is_file()
    assert (spec_dir / "pages").is_dir()


def test_saved_yaml_reloads(reference, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _extract(tmp_path, reference)

    data = yaml.safe_load((tmp_path / "specs" / "ref" / "spec.yaml").read_text())
    assert data["metadata"]["name"] == "ref"


def test_palette_follows_the_slides_not_the_stock_theme(reference, tmp_path, monkeypatch):
    """A deck that colours its own shapes must not be described by Office blue."""
    monkeypatch.chdir(tmp_path)
    spec = _extract(tmp_path, reference)
    palette = spec.palette

    assert palette.accent1 == "#7E694F"       # the band, ranked by area
    assert "#7E694F" in palette.dominant
    # Stock accents are nowhere on the slides — they must not survive as if
    # they were this deck's brand colours.
    scalars = {v for v in palette.to_dict().values() if isinstance(v, str)}
    assert not {"#4472C4", "#ED7D31", "#A5A5A5"} & scalars


def test_used_colors_ranks_by_area(reference):
    from ppt_clone.spec.theme import extract_used_colors, extract_theme_colors

    ranked = extract_used_colors(str(reference), extract_theme_colors(str(reference)))
    assert ranked, "the band's fill should be found"
    assert ranked[0][0] == "#7E694F"          # 13.3in x 2in beats everything


def test_neutral_colors_are_recognised():
    from ppt_clone.spec.spec_model import is_neutral_color

    assert is_neutral_color("#FFFFFF") and is_neutral_color("#1E1E1E")
    assert is_neutral_color("#F5F5F4")
    assert not is_neutral_color("#7E694F") and not is_neutral_color("#5B371C")


def test_list_and_select_specs(reference, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _extract(tmp_path, reference)

    assert list_specs() == ["ref"]
    select_spec("ref")
    assert get_active_spec() == "ref"
    with pytest.raises(FileNotFoundError):
        select_spec("no-such-spec")
