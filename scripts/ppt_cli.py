#!/usr/bin/env python3
"""ppt-clone — read a reference deck's design spec, then replicate it.

The whole skill is one loop: **extract** the design DNA from a reference
`.pptx`, **generate** slides against it, **convert** them to native shapes.

  extract-spec <ref.pptx>     read the reference deck -> specs/<name>/
                              (palette, fonts, per-page layout + assets)
  generate-pptx               spec + outline -> .pptx (agent loop: generate SVG,
                              score vs spec, fix, then convert)
  convert <svg>... -o out.pptx    SVG -> native-shape .pptx
  list-specs / select-spec    manage the extracted specs
  qa-balance <png-dir>        per-page whitespace balance over rendered pages

Run from the skill root with the project venv:

  ./.venv/bin/python scripts/ppt_cli.py extract-spec template.pptx
  ./.venv/bin/python scripts/ppt_cli.py convert build/*.svg -o out.pptx
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def cmd_extract_spec(args: argparse.Namespace) -> int:
    """Read a reference PPTX and write its design spec to specs/<name>/."""
    from ppt_clone.spec.enhanced_extractor import SpecExtractor

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: PPTX file not found: {input_path}", file=sys.stderr)
        return 1

    extractor = SpecExtractor()
    spec = extractor.extract(input_path, name=getattr(args, "name", None))
    extractor.save(spec)

    print(f"Spec saved: specs/{spec.metadata.get('name', 'spec')}/")
    print(f"  Colors: {len(spec.palette.to_dict())} palette entries")
    dominant = getattr(spec.palette, "dominant", None)
    if dominant:
        # What the slides actually paint with, ranked by area — the honest
        # answer when the deck ships a stock theme and colours its own shapes.
        print(f"  In use: {', '.join(dominant[:5])}")
    print(f"  Fonts: {spec.typography.heading_family or 'unknown'} / "
          f"{spec.typography.body_family or 'unknown'}")
    print(f"  Pages: {len(spec.pages)} → {', '.join(spec.page_types_found)}")
    if spec.layout_sub_types_found:
        print(f"  Layouts: {', '.join(spec.layout_sub_types_found)}")
    print(f"  VL analysis: {'enabled' if extractor.config.enabled else 'disabled'}")
    return 0


def cmd_generate_pptx(args: argparse.Namespace) -> int:
    """Generate a PPTX from an extracted spec plus a content outline."""
    from ppt_clone.ppt_generator import generate_pptx

    spec_dir = Path(args.spec)
    outline_path = Path(args.outline)
    if not spec_dir.exists():
        print(f"Error: Spec directory not found: {spec_dir}", file=sys.stderr)
        return 1
    if not outline_path.exists():
        print(f"Error: Outline file not found: {outline_path}", file=sys.stderr)
        return 1

    output = Path(args.output)

    # In CLI mode there is no LLM, so the per-slide SVG generator is a
    # placeholder; under an AI runtime the agent supplies the real one.
    def generate_callback(prompt: str) -> str:
        import warnings
        warnings.warn("generate-pptx in CLI mode uses placeholder SVG. "
                      "Use an AI runtime for LLM-backed generation.", RuntimeWarning)
        return ('<svg viewBox="0 0 1280 720" xmlns="http://www.w3.org/2000/svg">'
                '<rect width="1280" height="720" fill="#FFFFFF"/>'
                '<text x="100" y="100" font-family="Arial" font-size="24">Placeholder</text>'
                '</svg>')

    print(f"Replicating spec: {spec_dir.name}")
    print(f"Outline: {outline_path.name}  Workers: {args.workers}")
    result = generate_pptx(spec_dir=spec_dir, outline_path=outline_path,
                           output_path=output, generate_callback=generate_callback,
                           max_workers=args.workers)

    print(f"\nDone: {result.passed_count}/{len(result.slide_results)} slides ≥ threshold, "
          f"avg score {result.avg_score:.1%}")
    for sr in result.slide_results:
        mark = "✓" if sr.passed else "⚠"
        print(f"  {mark} slide {sr.slide_index}: {sr.page_type}/{sr.layout_sub_type} "
              f"score={sr.best_score:.0%} iter={sr.iterations}")
    if result.output_path:
        print(f"  Output: {result.output_path}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    """Convert SVG files to a native-shape PPTX."""
    from ppt_clone.converter import create_pptx_with_native_svg

    svg_files = [Path(f) for f in args.input]
    missing = [f for f in svg_files if not f.exists()]
    if missing:
        print(f"Error: SVG files not found: {missing}", file=sys.stderr)
        return 1

    # Slides left over from an earlier, longer build are easy to convert by
    # accident when passing a directory/glob — they join the deck silently.
    given = {f.resolve() for f in svg_files}
    stale = [s for f in svg_files for s in sorted(f.parent.glob("*.svg"))
             if s.resolve() not in given]
    stale = list(dict.fromkeys(stale))
    if stale:
        print(f"Warning: {len(stale)} SVG(s) in {svg_files[0].parent} are NOT in this "
              f"conversion and will be ignored: "
              f"{', '.join(s.name for s in stale[:6])}"
              + (" …" if len(stale) > 6 else ""), file=sys.stderr)

    output = Path(args.output)
    if create_pptx_with_native_svg(svg_files, output, use_native_shapes=True, verbose=True):
        print(f"PPTX created: {output} ({len(svg_files)} slides)")
        return 0
    print("Error: conversion failed", file=sys.stderr)
    return 1


def cmd_qa_balance(args: argparse.Namespace) -> int:
    """Measure per-page content balance from rendered slide PNGs."""
    from ppt_clone.layout_qa import main as qa_main

    argv = [args.directory, "--box", args.box, "--deck-width", str(args.deck_width),
            "--max-gap", str(args.max_gap), "--slack", str(args.slack)]
    if args.pattern:
        argv += ["--pattern", args.pattern]
    return qa_main(argv)


def cmd_list_specs(args: argparse.Namespace) -> int:
    from ppt_clone.cli.spec_commands import list_specs, get_active_spec

    specs = list_specs()
    if not specs:
        print("No specs yet — run: ppt_cli.py extract-spec <reference.pptx>")
        return 0
    active = get_active_spec()
    for spec_path in specs:
        mark = "★" if spec_path.name.replace(".yaml", "") == active else " "
        print(f"{mark} {spec_path.stem}")
    return 0


def cmd_select_spec(args: argparse.Namespace) -> int:
    from ppt_clone.cli.spec_commands import select_spec

    select_spec(args.name)
    print(f"Active spec set to: {args.name}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ppt-clone — extract a reference deck's design spec, then replicate it",
        prog="ppt-clone")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("extract-spec", help="Read a reference PPTX -> specs/<name>/")
    p.add_argument("input", help="Reference PPTX file")
    p.add_argument("--name", help="Spec name (default: filename stem)")

    p = sub.add_parser("generate-pptx", help="Spec + outline -> PPTX (agent loop)")
    p.add_argument("--spec", required=True, help="Spec directory (specs/<name>/)")
    p.add_argument("--outline", required=True, help="Content outline YAML")
    p.add_argument("-o", "--output", default="output.pptx", help="Output PPTX path")
    p.add_argument("--workers", type=int, default=4, help="Parallel workers (default 4)")

    p = sub.add_parser("convert", help="SVG -> native-shape PPTX")
    p.add_argument("input", nargs="+", help="SVG file(s)")
    p.add_argument("-o", "--output", required=True, help="Output PPTX path")

    sub.add_parser("list-specs", help="List extracted specs")
    p = sub.add_parser("select-spec", help="Set the active spec")
    p.add_argument("name", help="Spec name")

    p = sub.add_parser("qa-balance", help="Per-page whitespace balance from renders")
    p.add_argument("directory", help="Directory of rendered page PNGs")
    p.add_argument("--box", required=True,
                   help="content band left,top,right,bottom (deck pt)")
    p.add_argument("--deck-width", type=float, default=1280.0,
                   help="deck width matching --box units (default 1280)")
    p.add_argument("--pattern", default=None, help="glob for page images")
    p.add_argument("--max-gap", type=float, default=70.0,
                   help="flag pages whose larger margin exceeds this")
    p.add_argument("--slack", type=float, default=10.0,
                   help="allowed top/bottom difference for 'centred'")

    args = ap.parse_args()
    handler = {"extract-spec": cmd_extract_spec, "generate-pptx": cmd_generate_pptx,
               "convert": cmd_convert, "list-specs": cmd_list_specs,
               "select-spec": cmd_select_spec, "qa-balance": cmd_qa_balance}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
