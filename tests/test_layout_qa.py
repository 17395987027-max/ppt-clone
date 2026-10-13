"""Content-balance measurement used to police whitespace across a deck."""

from __future__ import annotations

from PIL import Image, ImageDraw

from ppt_clone.layout_qa import PageBalance, measure_dir, measure_page, scale_box

DECK_W, IMG_W = 960.0, 1200           # deck coordinate space vs. its 1.25x render
BAND = (40, 160, 920, 500)            # deck pt: below the header band, above the footer


def _page(tmp_path, block, name="p-01.png", size=(1200, 675)):
    im = Image.new("RGB", size, (255, 255, 255))
    ImageDraw.Draw(im).rectangle(block, fill=(60, 66, 71))
    path = tmp_path / name
    im.save(path)
    return str(path)


def test_centred_block_measures_equal_margins(tmp_path):
    # A block sitting in the middle of the band is balanced.
    box = scale_box(BAND, DECK_W, IMG_W)
    cy = (box[1] + box[3]) // 2
    path = _page(tmp_path, (600, cy - 60, 900, cy + 60))
    res = measure_page(path, box)
    assert res is not None
    assert abs(res.top - res.bottom) <= 2
    assert res.balanced()


def test_top_heavy_block_is_flagged_as_unbalanced(tmp_path):
    box = scale_box(BAND, DECK_W, IMG_W)
    path = _page(tmp_path, (600, box[1], 900, box[1] + 80))
    res = measure_page(path, box)
    assert res is not None
    assert res.bottom > res.top + 10
    assert not res.balanced()


def test_empty_band_reports_nan(tmp_path):
    box = scale_box(BAND, DECK_W, IMG_W)
    path = _page(tmp_path, (0, 0, 1, 1))  # the only ink sits outside the band
    res = measure_page(path, box)
    assert res is not None and res.top != res.top  # NaN


def test_measure_dir_reads_every_render(tmp_path):
    box = scale_box(BAND, DECK_W, IMG_W)
    cy = (box[1] + box[3]) // 2
    for i in range(3):
        _page(tmp_path, (600, cy - 40, 900, cy + 40), name=f"p-0{i + 1}.png")
    res = measure_dir(str(tmp_path), BAND, deck_width=DECK_W)
    assert [r.page for r in res] == ["p-01.png", "p-02.png", "p-03.png"]
    assert all(r.balanced() for r in res)


def test_scale_box_maps_deck_points_to_pixels():
    assert scale_box((0, 0, 960, 540), DECK_W, IMG_W) == (0, 0, 1200, 675)
    assert PageBalance("x", 10, 10, 0, 0).balanced()
