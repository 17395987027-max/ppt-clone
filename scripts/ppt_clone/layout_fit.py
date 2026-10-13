"""Auto-fit a vertical block into a content band.

A fixed font size with top-aligned content is the classic "content crowded into
the top half" defect: long content overflows the band, short content leaves the
bottom third empty. The rule that works — and that took several iterations to
get right on a real deck — is:

1. walk a **descending size ladder** and take the *largest* size that fits;
2. spend the leftover height on the block's gaps, but **cap** that growth (an
   unbounded gap looks broken, not generous);
3. **centre** whatever is still left over.

``fit_block`` is that arithmetic on its own, so every layout (labelled rows,
bullets, cards) shares it instead of re-deriving it. Pair it with
``layout_qa.py`` to confirm the result on the render.

The ``measure`` callback returns ``(content_height, base_gap, n_gaps)`` for a
candidate size — gap count is one less than the number of items in the block.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

Measure = Callable[[float], "tuple[float, float, int]"]


@dataclass(frozen=True)
class Fit:
    """Chosen size, the gap to lay items out with, and where to start."""

    size: float
    gap: float
    height: float
    offset: float  # distance from the top of the room to the top of the block


def fit_block(size_ladder: Sequence[float], room: float, measure: Measure,
              gap_cap: float = 1.0) -> Fit:
    """Fit a block of items into ``room`` px of vertical space.

    ``size_ladder`` must be descending (largest first). ``gap_cap`` limits how
    far a gap may grow, as a multiple of its base value.
    """
    if not size_ladder:
        raise ValueError("size_ladder must not be empty")

    size = size_ladder[-1]
    for candidate in size_ladder:
        height, _gap, _n = measure(candidate)
        size = candidate
        if height <= room:
            break

    height, gap, n_gaps = measure(size)
    if n_gaps > 0 and height < room:
        grow = min(room - height, int(gap * gap_cap) * n_gaps)
        gap += grow // n_gaps
        height += grow
    return Fit(size, gap, height, max(0.0, (room - height) // 2))
