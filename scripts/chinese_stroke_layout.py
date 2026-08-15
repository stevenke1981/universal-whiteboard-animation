#!/usr/bin/env python3
"""中文字場景排版、時序與 annotation element 建構工具。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFont

from chinese_stroke_data import font_glyph_contours, is_han_character, path_length, transform_font_contours

STROKE_ORDER_RULES = (
    "以逐字筆畫資料的 strokes 陣列為準；每筆沿 medians 起點到終點書寫；"
    "複合筆畫不中斷；文字按原 Unicode 字元處理，不自動簡繁轉換；"
    "缺少權威資料時只能標記為近似，不得宣稱筆順正確。"
)

DEFAULT_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\kaiu.ttf",
    r"C:\Windows\Fonts\msjh.ttc",
    "/System/Library/Fonts/Supplemental/BiauKai.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/truetype/arphic-bkai00mp/bkai00mp.ttf",
    "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)

def find_default_font() -> Path | None:
    env = os.environ.get("WHITEBOARD_FONT") or os.environ.get("CHINESE_FONT")
    candidates = ([env] if env else []) + list(DEFAULT_FONT_CANDIDATES)
    for value in candidates:
        if value and Path(value).is_file():
            return Path(value).resolve()
    return None

def _hex_to_bgr(value: str) -> tuple[int, int, int]:
    digits = value.strip().lstrip("#")
    if len(digits) != 6:
        raise ValueError(f"非法色碼: {value}")
    red = int(digits[0:2], 16)
    green = int(digits[2:4], 16)
    blue = int(digits[4:6], 16)
    return blue, green, red

def _font_object(font_path: str | Path | None, size: int) -> ImageFont.FreeTypeFont | None:
    if font_path is None:
        return None
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError as exc:
        raise ValueError(f"無法開啟中文字型: {font_path}: {exc}") from exc

def _character_advance(character: str, font: ImageFont.FreeTypeFont | None, size: int) -> float:
    if character.isspace():
        return size * 0.5
    if is_han_character(character):
        return float(size)
    if font is not None:
        return max(size * 0.28, float(font.getlength(character)))
    return size * 0.55

def plan_layout(
    text: str,
    font_path: str | None,
    size: int,
    width: int,
    height: int,
    char_gap: float = 0.0,
) -> list[tuple[float, float]]:
    """水平中文排版：原字序由左至右，整句在畫布置中。"""
    font = _font_object(font_path, size)
    advances = [_character_advance(character, font, size) for character in text]
    total = sum(advances) + char_gap * max(0, len(text) - 1)
    x = (width - total) / 2.0
    y = (height - size) / 2.0
    origins: list[tuple[float, float]] = []
    for advance in advances:
        origins.append((x, y))
        x += advance + char_gap
    return origins

def decompose_contours(
    font_path: str,
    char: str,
    upem: int,
    scale: float,
    origin: tuple[float, float],
) -> list[list[tuple[float, float]]]:
    """相容舊 API：以 fontTools 展開 glyph 輪廓；不是權威筆畫資料。"""
    contours, actual_upem = font_glyph_contours(font_path, char)
    size = max(1.0, float(upem) * scale)
    return transform_font_contours(contours, origin, size, actual_upem)

def stroke_key(bbox: tuple[float, float, float, float], char_height: float):
    """舊版字型輪廓近似排序鍵；僅供 ``font-heuristic`` fallback。"""
    x0, y0, x1, y1 = bbox
    width, height = x1 - x0, y1 - y0
    layer = int(y0 / max(1.0, char_height * 0.34))
    horizontal_first = 0 if width >= height else 1
    return layer, horizontal_first, x0

def _save_mask(mask: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, mode="L").save(path)

def _relative_posix(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()

def _duration_ms(
    points: list[tuple[float, float]],
    *,
    base_ms: int,
    ms_per_px: float,
    min_ms: int,
    max_ms: int,
) -> int:
    length = path_length(points)
    return max(min_ms, min(max_ms, int(round(base_ms + length * ms_per_px))))

def _new_element(
    *,
    sequence: int,
    char_index: int,
    character: str,
    stroke_index: int,
    stroke_count: int,
    region: tuple[int, int, int, int],
    start_ms: int,
    duration_ms: int,
    mask_path: str,
    source: str,
    confidence: str,
    median: list[tuple[float, float]] | None,
    text: str,
    element_type: str = "text-stroke",
) -> dict[str, Any]:
    x0, y0, x1, y1 = region
    reveal: dict[str, Any] = {
        "mode": "write",
        "direction": "auto",
        "startMs": start_ms,
        "durationMs": duration_ms,
        "protectedRegions": [],
    }
    hand_path: dict[str, Any] | None = None
    if median and len(median) >= 2:
        points = [[round(x, 3), round(y, 3)] for x, y in median]
        hand_path = {
            "points": points,
            "start": points[0],
            "end": points[-1],
            "coordinateSpace": "canvas",
            "easing": "linear",
            "penLifts": [],
        }
        dx = median[-1][0] - median[0][0]
        dy = median[-1][1] - median[0][1]
        reveal["direction"] = "left_to_right" if abs(dx) >= abs(dy) and dx >= 0 else (
            "right_to_left" if abs(dx) >= abs(dy) else (
                "top_to_bottom" if dy >= 0 else "bottom_to_top"
            )
        )

    element: dict[str, Any] = {
        "id": f"char-{char_index + 1}-stroke-{stroke_index}",
        "label": f"第 {char_index + 1} 字第 {stroke_index}/{stroke_count} 筆：{character}",
        "sequence": sequence,
        "type": element_type,
        "narrativeRole": "依正確筆順書寫中文字" if confidence == "authoritative" else "中文字型近似書寫",
        "subtitle": text,
        "subjectIds": [],
        "maskPolicy": "explicit",
        "strokeMask": mask_path,
        "strokeSource": source,
        "strokeOrderConfidence": confidence,
        "character": character,
        "characterIndex": char_index + 1,
        "strokeIndex": stroke_index,
        "strokeCount": stroke_count,
        "region": {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0},
        "reveal": reveal,
    }
    if hand_path:
        element["handPath"] = hand_path
    return element
