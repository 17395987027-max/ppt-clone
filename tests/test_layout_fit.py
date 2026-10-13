"""Vertical auto-fit: largest size that fits, capped gap growth, then centring."""

from __future__ import annotations

import pytest

from ppt_clone.layout_fit import fit_block

LADDER = [22, 21, 20, 19, 18, 17, 16, 15]


def _measure(lines_per_item, n_items, line_ratio=1.5, gap_ratio=1.05):
    """A fake layout: each item is `lines_per_item` lines at 1.5x the size."""
    def measure(size):
        lh = round(size * line_ratio)
        gap = round(size * gap_ratio)
        return lh * lines_per_item * n_items, gap, n_items - 1
    return measure


def test_dense_block_takes_the_largest_size_that_fits():
    # 5 items x 2 lines fits at 20pt (300px) but not at 22pt (330px).
    fit = fit_block(LADDER, room=300, measure=_measure(2, 5))
    assert fit.size == 20
    assert fit.height <= 300
    assert fit.offset == 0                     # exactly full, nothing to centre


def test_content_taller_than_the_band_falls_back_to_the_smallest_size():
    # 36 lines can never fit in 300px: return the smallest size, flag by layout
    # rather than silently overflowing.
    fit = fit_block(LADDER, room=300, measure=_measure(6, 6))
    assert fit.size == LADDER[-1]
    assert fit.offset == 0


def test_sparse_block_takes_the_largest_size_and_centres():
    fit = fit_block(LADDER, room=366, measure=_measure(2, 3))
    assert fit.size == 22
    assert fit.offset > 0                      # leftover height goes to the top
    assert fit.height <= 366


def test_gap_growth_is_capped():
    # 3 two-line items at 22pt measure ~178px; the gap may at most double.
    def measure(size):
        return 178.0, 23.0, 2
    fit = fit_block(LADDER, room=366, measure=measure)
    assert fit.gap <= 46 + 1
    assert fit.offset > 0                      # capped growth, rest is centred


def test_single_item_cannot_grow_its_gap():
    fit = fit_block(LADDER, room=366, measure=lambda s: (40.0, 20.0, 0))
    assert fit.gap == 20.0
    assert fit.offset == 163.0                 # centred


def test_block_never_exceeds_the_room_when_it_can_fit():
    for lines in (1, 2, 3, 6):
        for items in (1, 3, 6):
            m = _measure(lines, items)
            smallest = m(LADDER[-1])[0]
            fit = fit_block(LADDER, room=300, measure=m)
            if smallest <= 300:
                assert fit.height <= 300 + 0.001, (lines, items, fit)
            else:
                assert fit.size == LADDER[-1] and fit.offset == 0


def test_empty_ladder_is_rejected():
    with pytest.raises(ValueError):
        fit_block([], 300, _measure(1, 1))
