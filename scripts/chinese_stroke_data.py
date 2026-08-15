#!/usr/bin/env python3
"""相容匯出：中文字筆畫資料載入與幾何工具。"""
from chinese_stroke_repository import CharacterStrokeData, StrokeDataError, StrokeDataRepository
from chinese_stroke_geometry import (
    HANZI_COORD_SIZE,
    HANZI_TOP_Y,
    FlattenPen,
    blend_mask,
    contours_to_mask,
    font_glyph_contours,
    is_han_character,
    mask_bbox,
    parse_svg_contours,
    path_length,
    transform_font_contours,
    transform_hanzi_contours,
    transform_hanzi_point,
)

__all__ = [
    "CharacterStrokeData", "StrokeDataError", "StrokeDataRepository",
    "HANZI_COORD_SIZE", "HANZI_TOP_Y", "FlattenPen", "blend_mask",
    "contours_to_mask", "font_glyph_contours", "is_han_character",
    "mask_bbox", "parse_svg_contours", "path_length", "transform_font_contours",
    "transform_hanzi_contours", "transform_hanzi_point",
]
