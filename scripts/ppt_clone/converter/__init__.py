"""ppt_clone.converter — SVG to native DrawingML shapes (forked from ppt-master).

Public API:
    convert_svg_to_slide_shapes(): SVG -> DrawingML slide XML
    create_pptx_with_native_svg(): build a PPTX from SVG files
"""

from .converter import convert_svg_to_slide_shapes
from .builder import create_pptx_with_native_svg

__all__ = [
    'convert_svg_to_slide_shapes',
    'create_pptx_with_native_svg',
]
