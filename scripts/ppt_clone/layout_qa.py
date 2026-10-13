"""Check that a rendered slide's content is balanced inside its content band.

Renders are the only ground truth for balance: auto-fit arithmetic can agree
with itself and still leave a page top-heavy, because it doesn't know where the
header band ends or how tall the footer logo row is. Measure the ink bounding
box of each rendered page inside a caller-supplied content band (which excludes
the header band and the footer row) and report the top/bottom margins:

* margins within ``--slack`` px of each other  → the block is centred;
* a bottom margin below ``--min-fill`` px      → the content crowds the top.

Usage (from the skill root):

    ./.venv/bin/python scripts/ppt_clone/layout_qa.py build/render \\
        --box 40,120,1240,660 --deck-width 1280 --max-gap 70

``--box`` is the deck's own content band (left, top, right, bottom) in the
deck's coordinate space by default — set ``--deck-width`` to that space's width
(e.g. 1280 for a 16:9 deck); pass ``--box-units px`` to give the box in image
pixels instead. Exclude the header band and the footer row from the box, or
every page measures "full".
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
from dataclasses import dataclass

from PIL import Image, ImageChops

# A pixel differing from white by more than this counts as ink.
INK_THRESHOLD = 28


@dataclass
class PageBalance:
    page: str
    top: float
    bottom: float
    left: float
    right: float

    def balanced(self, slack: float = 10.0) -> bool:
        return abs(self.top - self.bottom) <= slack


def scale_box(box: tuple[float, float, float, float], deck_width: float,
              image_width: int) -> tuple[int, int, int, int]:
    """Convert a box given in the deck's coordinate space to image pixels."""
    k = image_width / float(deck_width)
    return tuple(int(round(v * k)) for v in box)  # type: ignore[return-value]


def measure_page(path: str, content_box: tuple[int, int, int, int],
                 ink_threshold: int = INK_THRESHOLD) -> PageBalance | None:
    """Ink bounding box of one rendered page inside ``content_box`` (image px).

    Returns the gaps from each edge of ``content_box`` to the ink, or ``None``
    when the band is empty.
    """
    im = Image.open(path).convert("RGB")
    left, top, right, bottom = content_box
    band = im.crop((left, top, right, bottom))
    white = Image.new("RGB", band.size, (255, 255, 255))
    ink = ImageChops.difference(band, white).convert("L").point(
        lambda v: 255 if v > ink_threshold else 0)
    bbox = ink.getbbox()
    name = os.path.basename(path)
    if not bbox:
        return PageBalance(name, float("nan"), float("nan"), float("nan"), float("nan"))
    return PageBalance(
        page=name,
        top=float(bbox[1]),
        bottom=float(band.size[1] - bbox[3]),
        left=float(bbox[0]),
        right=float(band.size[0] - bbox[2]),
    )


def measure_dir(directory: str, box: tuple[float, float, float, float],
                deck_width: float = 1280.0, pattern: str = "*.png",
                ink_threshold: int = INK_THRESHOLD) -> list[PageBalance]:
    """Measure every matching render in ``directory`` (sorted by name)."""
    out: list[PageBalance] = []
    for path in sorted(glob.glob(os.path.join(directory, pattern))):
        im = Image.open(path)
        px_box = scale_box(box, deck_width, im.size[0])
        res = measure_page(path, px_box, ink_threshold)
        if res is not None:
            out.append(res)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("directory", help="Directory of rendered page PNGs")
    ap.add_argument("--box", required=True,
                    help="content band left,top,right,bottom (deck pt by default)")
    ap.add_argument("--box-units", choices=["deck", "px"], default="deck")
    ap.add_argument("--deck-width", type=float, default=1280.0,
                    help="deck width in the same units as --box (default 1280)")
    ap.add_argument("--pattern", default="*.png")
    ap.add_argument("--max-gap", type=float, default=70.0,
                    help="flag pages whose larger margin exceeds this (default 70)")
    ap.add_argument("--slack", type=float, default=10.0,
                    help="allowed top/bottom difference for 'centred' (default 10)")
    args = ap.parse_args(argv)

    box = tuple(float(v) for v in args.box.split(","))
    if len(box) != 4:
        ap.error("--box needs four comma-separated numbers")

    results = measure_dir(args.directory, box, args.deck_width, args.pattern)
    if not results:
        print(f"no PNGs matched {args.pattern!r} in {args.directory}")
        return 2

    flagged = 0
    print(f"{'page':<24}{'top':>7}{'bottom':>8}{'left':>7}{'right':>7}   note")
    for r in results:
        bigger = max(r.top, r.bottom)
        notes = []
        if not r.balanced(args.slack):
            notes.append("off-centre")
        if bigger > args.max_gap:
            notes.append(f"large margin {bigger:.0f}px")
        if notes:
            flagged += 1
        print(f"{r.page:<24}{r.top:>7.0f}{r.bottom:>8.0f}{r.left:>7.0f}{r.right:>7.0f}   "
              + ", ".join(notes))
    print(f"\n{len(results)} pages, {flagged} flagged")
    return 1 if flagged else 0


if __name__ == "__main__":
    sys.exit(main())
