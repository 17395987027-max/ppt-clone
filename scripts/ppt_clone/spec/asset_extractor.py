"""Asset extraction — backgrounds, icons, and reusable decorative elements.

Extracts and CLASSIFIES visual assets:
  - BACKGROUND: Full-slide backgrounds (keep)
  - ICON: Small images in margins/corners, typically repeated (keep)
  - DECORATION: Accent shapes, lines, decorative image fills (keep)
  - CHART: Data visualizations (DISCARD — content-dependent)
  - CONTENT_IMAGE: Photos, screenshots in content area (DISCARD — content-dependent)

Classification rules:
  - chart/table shapes           → DISCARD
  - area < 3%                    → ICON
  - 3% ≤ area < 15%              → DECORATION
  - 15% ≤ area < 88%             → DECORATION (a framed photo block the
                                    layout is built around — not throwaway)
  - area ≥ 88%                   → BACKGROUND (a full-bleed ground)

Each kept asset also carries HOW it is used (``usage`` = background / hero /
decoration / icon, refined to mockup_frame / inset when one picture nests in
another via annotate_contains) plus ``crop`` (srcRect crop / stretched-to-fit).

All kept assets saved to specs/<name>/assets/.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from lxml import etree

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"


class AssetType(str, Enum):
    BACKGROUND = "background"
    ICON = "icon"
    DECORATION = "decoration"
    CHART = "chart"
    CONTENT_IMAGE = "content_image"


@dataclass
class AssetInfo:
    type: AssetType
    src: str
    description: str
    shape_name: str = ""
    position: dict = None
    size_ratio: float = 0.0  # fraction of slide area
    # How the picture is used: background | hero | decoration | icon — refined
    # to mockup_frame / inset when one picture sits inside another.
    usage: str = ""
    contains: str = ""       # src of the picture framed by this one
    inside: str = ""         # src of the frame this picture sits in
    crop: dict = None        # {"cropped": bool, "stretched": bool}
    rotation: float = 0.0    # degrees; a ground is often laid on a rotated rect

    def to_dict(self) -> dict:
        d = {"type": self.type.value, "src": self.src, "description": self.description}
        if self.shape_name:
            d["shape_name"] = self.shape_name
        if self.position:
            d["position"] = self.position
        if self.usage:
            d["usage"] = self.usage
        if self.contains:
            d["contains"] = self.contains
        if self.inside:
            d["inside"] = self.inside
        if self.crop:
            d["crop"] = self.crop
        if self.rotation:
            d["rotation"] = round(self.rotation, 1)
        return d


# A picture covering this much of the canvas is the page's ground, not a prop.
BACKGROUND_RATIO = 0.88


def _rotation_of(shape) -> float:
    """A shape's rotation in degrees, negative when counter-clockwise.

    A full-bleed ground is frequently a portrait rect turned -90° to cover a
    landscape slide; without the angle the replica lays the image flat and it
    comes out stretched.
    """
    try:
        return float(getattr(shape, "rotation", 0.0) or 0.0)
    except Exception:
        return 0.0


def usage_for(ratio: float) -> str:
    """Label a picture by the share of the canvas it covers."""
    if ratio >= BACKGROUND_RATIO:
        return "background"
    if ratio >= 0.15:
        return "hero"
    if ratio >= 0.03:
        return "decoration"
    return "icon"



# ── Classification ────────────────────────────────────────────────────


def classify_image(img_w_emu: int, img_h_emu: int,
                   slide_w_emu: int, slide_h_emu: int,
                   shape_name: str = "",
                   is_chart_shape: bool = False) -> AssetType:
    """Classify an image asset based on size and position.

    Uses heuristics:
        - Charts/tables       → DISCARD
        - < 3% slide area     → ICON (if named like one) / DECORATION
        - < 15% slide area    → DECORATION
        - ≥ 88% slide area    → BACKGROUND (a full-bleed ground)
        - 15–88% slide area   → DECORATION (a framed photo block belongs to
          the layout — throwing it away loses the design)
        - Everything else     → CONTENT_IMAGE (discard)
    """
    if is_chart_shape:
        return AssetType.CHART

    if slide_w_emu <= 0 or slide_h_emu <= 0:
        return AssetType.CONTENT_IMAGE

    slide_area = slide_w_emu * slide_h_emu
    img_area = img_w_emu * img_h_emu
    ratio = img_area / slide_area

    name_lower = shape_name.lower()

    # Very small → likely icon if named like one
    if ratio < 0.03:
        if any(kw in name_lower for kw in ["icon", "logo", "图标"]):
            return AssetType.ICON
        return AssetType.DECORATION

    # Small decorative elements
    if ratio < 0.15:
        if any(kw in name_lower for kw in ["icon", "logo", "图标", "decor", "装饰"]):
            return AssetType.ICON
        return AssetType.DECORATION

    # Full-bleed → the page's ground
    if ratio >= BACKGROUND_RATIO:
        return AssetType.BACKGROUND

    # Large but not full-bleed: a photo block the layout is built around.
    if ratio >= 0.15:
        return AssetType.DECORATION

    # Medium size in content area → content image (discard)
    return AssetType.CONTENT_IMAGE


# ── Background extraction ─────────────────────────────────────────────


def extract_background_image(slide, spec_dir: Path,
                              page_idx: int) -> dict[str, Any]:
    """Extract slide background image or color from inheritance chain.

    Walks: slide → slide layout → slide master → theme.

    Returns:
        {
            "type": "solid" | "image" | "gradient" | "none",
            "color": "#HEX" | "",
            "image": "assets/bg_000.png" | "",
            "description": "..." 
        }
    """
    result: dict[str, Any] = {
        "type": "solid",
        "color": "#FFFFFF",
        "image": "",
        "description": "White background",
    }

    # Level 1: Slide-level <p:bg>
    try:
        c_sld = slide.background._element
        bg = _find_bg(c_sld)
        if bg is not None:
            r = _parse_bg(bg, slide.part, spec_dir, page_idx, "slide")
            if r:
                return r
    except Exception:
        pass

    # Level 2: Slide layout
    try:
        layout = slide.slide_layout
        bg = _find_bg(layout._element)
        if bg is not None:
            r = _parse_bg(bg, layout.part, spec_dir, page_idx, "layout")
            if r:
                return r
    except Exception:
        pass

    # Level 3: Slide master
    try:
        master = slide.slide_layout.slide_master
        bg = _find_bg(master._element)
        if bg is not None:
            r = _parse_bg(bg, master.part, spec_dir, page_idx, "master")
            if r:
                return r
    except Exception:
        pass

    return result


def _find_bg(parent: etree._Element) -> etree._Element | None:
    """Find <p:bg> element under a parent (slide/layout/master root).

    <p:bg> may be a direct child of <p:sldMaster>/<p:sldLayout>, or nested
    inside their <p:cSld>, so search descendants rather than children only.
    """
    bg = parent.find(f"{{{P_NS}}}bg")
    if bg is not None:
        return bg
    return parent.find(f".//{{{P_NS}}}bg")


def _parse_bg(bg_elem: etree._Element, part, spec_dir: Path,
              page_idx: int, source: str) -> dict[str, Any] | None:
    """Parse a <p:bg> element. ``part`` is the part that owns bg_elem
    (slide/layout/master) — needed to resolve image relationship ids."""
    bg_pr = bg_elem.find(f"{{{P_NS}}}bgPr")
    if bg_pr is None:
        return None

    result: dict[str, Any] = {}

    # Image fill (blipFill)
    blip_fill = bg_pr.find(f"{{{A_NS}}}blipFill")
    if blip_fill is not None:
        img_path = _extract_blip(blip_fill, part, spec_dir, f"bg_{page_idx:03d}")
        if img_path:
            return {
                "type": "image",
                "color": "",
                "image": img_path,
                "description": f"Background image (from {source})",
            }

    # Gradient fill
    grad_fill = bg_pr.find(f"{{{A_NS}}}gradFill")
    if grad_fill is not None:
        stops = []
        gs_lst = grad_fill.find(f"{{{A_NS}}}gsLst")
        if gs_lst is not None:
            for gs in gs_lst.findall(f"{{{A_NS}}}gs"):
                pos = int(gs.get("pos", 0)) / 100000.0
                color = _resolve_color(gs[0]) if list(gs) else None
                stops.append({"pos": round(pos, 2), "color": color})
        return {
            "type": "gradient",
            "color": "",
            "image": "",
            "description": f"Gradient background ({len(stops)} stops, from {source})",
            "gradient_stops": stops,
        }

    # Solid fill
    solid = bg_pr.find(f"{{{A_NS}}}solidFill")
    if solid is not None and list(solid):
        color = _resolve_color(list(solid)[0])
        if color and color.startswith("#"):
            return {
                "type": "solid",
                "color": color,
                "image": "",
                "description": f"Solid background {color} (from {source})",
            }

    return None


def _extract_blip(blip_fill: etree._Element, part, spec_dir: Path,
                  base_name: str) -> str | None:
    """Extract image from a blipFill element to assets/ directory.

    ``part`` must be the part that owns the blipFill (slide/layout/master),
    since the r:embed id is resolved against that part's relationships.
    """
    blip = blip_fill.find(f"{{{A_NS}}}blip")
    if blip is None:
        return None

    embed_id = blip.get(f"{{{R_NS}}}embed")
    if not embed_id:
        return None

    try:
        rel = part.rels[embed_id]
        image = rel.target_part
        blob = image.blob
        content_type = image.content_type

        ext = _content_type_to_ext(content_type)
        assets_dir = spec_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{base_name}.{ext}"
        filepath = assets_dir / filename
        filepath.write_bytes(blob)
        return f"assets/{filename}"
    except Exception:
        return None


# ── Shape image extraction ────────────────────────────────────────────


def extract_shape_assets(shape, spec_dir: Path, page_idx: int,
                          slide_w_emu: int = 0, slide_h_emu: int = 0,
                          img_counter: list[int] | None = None,
                          seen: dict | None = None
                          ) -> list[AssetInfo]:
    """Extract and classify images from a shape (Picture, image fill, group children).

    Only keeps: BACKGROUND, ICON, DECORATION.
    Discards: CHART, CONTENT_IMAGE.

    ``img_counter`` is shared by the caller so names stay unique across a page;
    ``seen`` maps a blob hash to an already-saved src, so one picture reused by
    many shapes is written once.
    """
    if img_counter is None:
        img_counter = [0]
    if seen is None:
        seen = {}
    results: list[AssetInfo] = []

    # Direct Picture shapes
    try:
        from pptx.shapes.picture import Picture
        if isinstance(shape, Picture):
            asset = _extract_picture_asset(shape, spec_dir, page_idx,
                                            img_counter, slide_w_emu, slide_h_emu,
                                            seen)
            if asset and asset.type in (AssetType.BACKGROUND, AssetType.ICON,
                                         AssetType.DECORATION):
                results.append(asset)
            return results
    except ImportError:
        pass

    # Skip chart/table shapes
    try:
        if hasattr(shape, "has_table") and shape.has_table:
            return results
        if hasattr(shape, "chart"):
            shape.chart
            return results
    except Exception:
        pass

    # Shapes with image fill
    try:
        if hasattr(shape, "fill"):
            from pptx.enum.dml import MSO_FILL_TYPE
            if shape.fill.type == MSO_FILL_TYPE.PICTURE:
                asset = _extract_fill_asset(shape, spec_dir, page_idx,
                                             img_counter, slide_w_emu, slide_h_emu,
                                             seen)
                if asset and asset.type in (AssetType.BACKGROUND, AssetType.ICON,
                                             AssetType.DECORATION):
                    results.append(asset)
    except Exception:
        pass

    # Group shapes — recurse
    try:
        if hasattr(shape, "shapes"):
            for child in shape.shapes:
                child_results = extract_shape_assets(
                    child, spec_dir, page_idx, slide_w_emu, slide_h_emu,
                    img_counter, seen
                )
                results.extend(child_results)
    except Exception:
        pass

    return results


def _extract_picture_asset(picture, spec_dir: Path, page_idx: int,
                            img_counter: list[int],
                            slide_w_emu: int, slide_h_emu: int,
                            seen: dict | None = None) -> AssetInfo | None:
    """Extract and classify a Picture shape."""
    try:
        image = picture.image
        blob = image.blob
        ext = _content_type_to_ext(image.content_type)

        # Classify first (don't save charts/content)
        asset_type = classify_image(
            img_w_emu=(picture.width or 0),
            img_h_emu=(picture.height or 0),
            slide_w_emu=slide_w_emu,
            slide_h_emu=slide_h_emu,
            shape_name=picture.name,
        )

        if asset_type in (AssetType.CHART, AssetType.CONTENT_IMAGE):
            return AssetInfo(type=asset_type, src="", description=f"[DISCARDED] {picture.name}")

        ratio = ((picture.width or 0) * (picture.height or 0)) / (slide_w_emu * slide_h_emu) if slide_w_emu and slide_h_emu else 0.0
        usage = usage_for(ratio)
        crop = _describe_crop(picture, blob, ext)

        # Save (reuse an identical already-saved blob)
        assets_dir = spec_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        prefix = {"background": "bac", "hero": "pho", "decoration": "dec",
                  "icon": "ico"}.get(usage, "dec")
        digest = hashlib.sha1(blob).hexdigest()
        if seen is not None and digest in seen:
            filename = seen[digest]
        else:
            n = img_counter[0]
            img_counter[0] += 1
            filename = f"{prefix}_{page_idx:02d}_{n:02d}.{ext}"
            (assets_dir / filename).write_bytes(blob)
            if seen is not None:
                seen[digest] = filename

        x = (picture.left or 0) / 914400
        y = (picture.top or 0) / 914400
        w = (picture.width or 0) / 914400
        h = (picture.height or 0) / 914400

        detail = f"{usage} ({w:.1f}x{h:.1f}in, at {x:.1f},{y:.1f}, {ratio:.0%} of canvas)"
        if crop.get("cropped"):
            detail += ", cropped"
        if crop.get("stretched"):
            detail += ", stretched to fit"

        return AssetInfo(
            type=asset_type,
            src=f"assets/{filename}",
            shape_name=picture.name,
            position={"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)},
            description=f"{asset_type.value}: {filename} — {detail}",
            size_ratio=ratio,
            usage=usage,
            crop=crop,
            rotation=_rotation_of(picture),
        )
    except Exception:
        return None


def extract_page_background(slide, spec_dir: Path, page_idx: int,
                            slide_w_emu: int, slide_h_emu: int) -> dict[str, Any] | None:
    """Find the image that grounds this page.

    A background set through ``<p:bg>`` is handled elsewhere. Plenty of decks
    instead lay a full-bleed image on the slide, the layout or the master — as
    a picture, a picture inside a group, or a shape with a picture fill.
    Without this check such a page is described as white and the replica comes
    out with no ground at all.

    Returns a background dict (same shape as extract_background_image) or None.
    """
    if not slide_w_emu or not slide_h_emu:
        return None
    try:
        from pptx.shapes.picture import Picture
    except ImportError:
        return None

    def _blob_of(shape):
        """Return (blob, content_type) for a picture or a picture-filled shape."""
        if isinstance(shape, Picture):
            try:
                return shape.image.blob, shape.image.content_type
            except Exception:
                return None
        # A shape whose fill is an image — walk its own blipFill relationship.
        try:
            match = re.search(r'<a:blip[^>]*r:embed="([^"]*)"', shape._element.xml)
            if not match:
                return None
            rel = shape.part.rels.get(match.group(1))
            if not rel:
                return None
            return rel.target_part.blob, rel.target_part.content_type
        except Exception:
            return None

    def _scan(shapes, source: str):
        for shape in shapes:
            try:
                ratio = ((shape.width or 0) * (shape.height or 0)) / (slide_w_emu * slide_h_emu)
            except Exception:
                ratio = 0.0
            # Group shapes: the ground is often nested one level in.
            if hasattr(shape, "shapes") and not isinstance(shape, Picture):
                try:
                    found = _scan(shape.shapes, source)
                    if found:
                        return found
                except Exception:
                    pass
                continue
            if ratio < BACKGROUND_RATIO:
                continue
            got = _blob_of(shape)
            if not got:
                continue
            blob, content_type = got
            ext = _content_type_to_ext(content_type)
            assets_dir = spec_dir / "assets"
            assets_dir.mkdir(parents=True, exist_ok=True)
            filename = f"bg_{page_idx:03d}.{ext}"
            (assets_dir / filename).write_bytes(blob)
            rot = _rotation_of(shape)
            return {
                "type": "image",
                "color": "",
                "image": f"assets/{filename}",
                "rotation": rot,
                "description": (f"Full-bleed background image "
                                f"({ratio:.0%} of the canvas, from the {source}"
                                + (f", rotated {rot:g}°" if rot else "") + ")"),
            }
        return None

    for source, shapes in _background_sources(slide):
        found = _scan(shapes, source)
        if found:
            return found
    return None


def _background_sources(slide):
    """Layers to search for a ground, in front-to-back order."""
    sources = [("slide", slide.shapes)]
    try:
        sources.append(("layout", slide.slide_layout.shapes))
        sources.append(("master", slide.slide_layout.slide_master.shapes))
    except Exception:
        pass
    return sources


def _describe_crop(picture, blob: bytes, ext: str) -> dict[str, bool]:
    """Say whether a picture is cropped (srcRect) or distorted to fit."""
    cropped = False
    try:
        src_rect = picture._element.find(f".//{{{A_NS}}}blipFill/{{{A_NS}}}srcRect")
        if src_rect is not None:
            cropped = any(int(src_rect.get(k) or 0) != 0 for k in ("l", "t", "r", "b"))
    except Exception:
        pass

    stretched = False
    try:
        from PIL import Image
        nat_w, nat_h = Image.open(io.BytesIO(blob)).size
        if nat_w and nat_h and picture.width and picture.height:
            native = nat_w / nat_h
            placed = picture.width / picture.height
            stretched = abs(placed - native) / native > 0.02
    except Exception:
        pass

    return {"cropped": cropped, "stretched": stretched}


def annotate_contains(assets: list, tol: float = 0.15) -> None:
    """Mark pictures that sit inside another picture (a photo in a mockup).

    The outer picture is the frame — a laptop, a phone, a card — and the inner
    one is the content shown in it. Knowing both makes the page reproducible:
    draw the frame, then drop the photo into its opening.

    A full-bleed ground (``usage == "background"``) wraps everything on the
    page, so it is never a frame — excluding it keeps the real mockup pair.
    """
    def box(a: AssetInfo) -> tuple[float, float, float, float]:
        p = a.position or {}
        return (p.get("x", 0.0), p.get("y", 0.0), p.get("w", 0.0), p.get("h", 0.0))

    def is_ground(a: AssetInfo) -> bool:
        return a.type == AssetType.BACKGROUND or a.usage == "background"

    for inner in assets:
        if (not inner.src or is_ground(inner)
                or inner.type == AssetType.ICON or inner.usage == "icon"):
            continue
        ix, iy, iw, ih = box(inner)
        best = None
        for outer in assets:
            if outer is inner or not outer.src or outer.inside or outer.contains:
                continue
            if is_ground(outer) or outer.type == AssetType.ICON:
                continue
            ox, oy, ow, oh = box(outer)
            if ow * oh <= iw * ih * 1.1:
                continue
            # A genuine inset fills a real opening, not a sliver of the frame.
            if iw * ih < 0.10 * ow * oh:
                continue
            if (ox - tol <= ix and oy - tol <= iy
                    and ox + ow + tol >= ix + iw and oy + oh + tol >= iy + ih):
                if best is None or ow * oh < box(best)[2] * box(best)[3]:
                    best = outer
        if best is not None:
            inner.inside = best.src
            inner.usage = "inset"
            best.contains = inner.src
            best.usage = "mockup_frame"


def _extract_fill_asset(shape, spec_dir: Path, page_idx: int,
                         img_counter: list[int],
                         slide_w_emu: int, slide_h_emu: int,
                         seen: dict | None = None) -> AssetInfo | None:
    """Extract and classify a shape's image fill."""
    try:
        # Classify first
        ratio = (((shape.width or 0) * (shape.height or 0)) / (slide_w_emu * slide_h_emu)
                 if slide_w_emu and slide_h_emu else 0.0)
        asset_type = classify_image(
            img_w_emu=(shape.width or 0),
            img_h_emu=(shape.height or 0),
            slide_w_emu=slide_w_emu,
            slide_h_emu=slide_h_emu,
            shape_name=shape.name,
        )

        if asset_type in (AssetType.CHART, AssetType.CONTENT_IMAGE):
            return AssetInfo(type=asset_type, src="", description=f"[DISCARDED] {shape.name} fill")

        # Extract blip embed from XML
        xml = shape._element.xml
        match = re.search(r'<a:blip[^>]*r:embed="([^"]*)"', xml)
        if not match:
            return None

        embed_id = match.group(1)
        rel = shape.part.rels.get(embed_id)
        if not rel:
            return None

        image = rel.target_part
        blob = image.blob
        ext = _content_type_to_ext(image.content_type)

        usage = usage_for(ratio)
        prefix = {"background": "bac", "hero": "pho", "decoration": "dec",
                  "icon": "ico"}.get(usage, "dec")
        assets_dir = spec_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha1(blob).hexdigest()
        if seen is not None and digest in seen:
            filename = seen[digest]
        else:
            n = img_counter[0]
            img_counter[0] += 1
            filename = f"{prefix}_{page_idx:02d}_{n:02d}.{ext}"
            (assets_dir / filename).write_bytes(blob)
            if seen is not None:
                seen[digest] = filename

        x = (shape.left or 0) / 914400
        y = (shape.top or 0) / 914400
        w = (shape.width or 0) / 914400
        h = (shape.height or 0) / 914400

        fill_crop = _describe_fill_crop(shape, blob)
        detail = f"{usage} (fill in '{shape.name}'"
        detail += ", zooms and crops" if fill_crop.get("cropped") else ""
        detail += ", stretched)" if fill_crop.get("stretched") else ")"

        return AssetInfo(
            type=asset_type,
            src=f"assets/{filename}",
            shape_name=shape.name,
            position={"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)},
            description=f"{asset_type.value}: {filename} — {detail}",
            size_ratio=ratio,
            usage=usage,
            crop=fill_crop,
            rotation=_rotation_of(shape),
        )
    except Exception:
        return None


# ── Helpers ────────────────────────────────────────────────────────────


def _describe_fill_crop(shape, blob: bytes) -> dict[str, bool]:
    """Say whether an image FILL zooms/crops or is stretched to its shape.

    A negative ``<a:fillRect>`` inset overscans the shape — the fill is scaled
    up and cropped, so the picture keeps its proportions. A plain stretch with
    no inset distorts it. Getting this wrong is why a ground image can come out
    squashed.
    """
    cropped = False
    try:
        xml = shape._element.xml
        m = re.search(r"<a:fillRect([^/]*)/>", xml)
        if m:
            for key in ("l", "t", "r", "b"):
                v = re.search(rf'{key}="(-?\d+)"', m.group(1))
                if v and int(v.group(1)) != 0:
                    cropped = True
                    break
    except Exception:
        pass

    stretched = False
    if not cropped:
        try:
            from PIL import Image
            nat_w, nat_h = Image.open(io.BytesIO(blob)).size
            if nat_w and nat_h and shape.width and shape.height:
                native = nat_w / nat_h
                placed = shape.width / shape.height
                stretched = abs(placed - native) / native > 0.02
        except Exception:
            pass

    return {"cropped": cropped, "stretched": stretched}


def _content_type_to_ext(content_type: str) -> str:
    return {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/gif": "gif",
        "image/bmp": "bmp",
        "image/tiff": "tiff",
        "image/x-emf": "emf",
        "image/x-wmf": "wmf",
        "image/svg+xml": "svg",
    }.get(content_type, "bin")


def _resolve_color(color_elem: etree._Element) -> str | None:
    """Resolve OOXML color element to hex string."""
    if color_elem is None:
        return None
    tag = etree.QName(color_elem.tag).localname
    if tag == "srgbClr":
        val = color_elem.get("val")
        return f"#{val.upper()}" if val else None
    if tag == "sysClr":
        val = color_elem.get("lastClr") or color_elem.get("val")
        return f"#{val.upper()}" if val else None
    if tag == "schemeClr":
        return f"@scheme:{color_elem.get('val')}"
    return None
