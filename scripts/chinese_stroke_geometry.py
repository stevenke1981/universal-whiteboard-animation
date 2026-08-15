#!/usr/bin/env python3
"""中文字 SVG／字型輪廓、座標轉換與 mask 幾何工具。"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from fontTools.pens.basePen import BasePen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont

from chinese_stroke_repository import StrokeDataError

HANZI_COORD_SIZE = 1024.0

HANZI_TOP_Y = 900.0

class FlattenPen(BasePen):
    """將 line/quadratic/cubic path 取樣為多邊形輪廓。"""

    def __init__(self, glyph_set=None, curve_steps: int = 18):
        super().__init__(glyph_set)
        self.curve_steps = max(4, curve_steps)
        self.contours: list[list[tuple[float, float]]] = []
        self.current: list[tuple[float, float]] = []

    def _flush(self, close: bool) -> None:
        if close and self.current and self.current[-1] != self.current[0]:
            self.current.append(self.current[0])
        if len(self.current) >= 3:
            self.contours.append(self.current[:])
        self.current.clear()

    def _moveTo(self, point) -> None:  # noqa: N802 - fontTools API
        self._flush(close=False)
        self.current.append((float(point[0]), float(point[1])))

    def _lineTo(self, point) -> None:  # noqa: N802 - fontTools API
        self.current.append((float(point[0]), float(point[1])))

    def _curveToOne(self, control1, control2, point) -> None:  # noqa: N802
        if not self.current:
            return
        p0 = self.current[-1]
        c1 = (float(control1[0]), float(control1[1]))
        c2 = (float(control2[0]), float(control2[1]))
        p1 = (float(point[0]), float(point[1]))
        for index in range(1, self.curve_steps + 1):
            t = index / self.curve_steps
            mt = 1.0 - t
            x = mt**3 * p0[0] + 3 * mt**2 * t * c1[0] + 3 * mt * t**2 * c2[0] + t**3 * p1[0]
            y = mt**3 * p0[1] + 3 * mt**2 * t * c1[1] + 3 * mt * t**2 * c2[1] + t**3 * p1[1]
            self.current.append((x, y))

    def _qCurveToOne(self, control, point) -> None:  # noqa: N802
        if not self.current:
            return
        p0 = self.current[-1]
        c = (float(control[0]), float(control[1]))
        p1 = (float(point[0]), float(point[1]))
        for index in range(1, self.curve_steps + 1):
            t = index / self.curve_steps
            mt = 1.0 - t
            x = mt**2 * p0[0] + 2 * mt * t * c[0] + t**2 * p1[0]
            y = mt**2 * p0[1] + 2 * mt * t * c[1] + t**2 * p1[1]
            self.current.append((x, y))

    def _closePath(self) -> None:  # noqa: N802
        self._flush(close=True)

    def _endPath(self) -> None:  # noqa: N802
        self._flush(close=False)

    def finish(self) -> list[list[tuple[float, float]]]:
        self._flush(close=False)
        return self.contours

def parse_svg_contours(path_data: str) -> list[list[tuple[float, float]]]:
    pen = FlattenPen()
    try:
        parse_path(path_data, pen)
    except Exception as exc:  # fontTools 可能丟多種 path parser 例外
        raise StrokeDataError(f"無法解析 SVG stroke path: {exc}") from exc
    contours = pen.finish()
    if not contours:
        raise StrokeDataError("SVG stroke path 沒有可繪製輪廓")
    return contours

def font_glyph_contours(font_path: str | Path, character: str) -> tuple[list[list[tuple[float, float]]], int]:
    """以 fontTools 展開字型 glyph；僅供沒有真實筆畫資料時的 fallback。"""
    font = TTFont(str(font_path), fontNumber=0)
    try:
        cmap = font.getBestCmap() or {}
        glyph_name = cmap.get(ord(character))
        if glyph_name is None:
            raise StrokeDataError(f"字型不包含字元 {character!r}: {font_path}")
        glyph_set = font.getGlyphSet()
        recorder = DecomposingRecordingPen(glyph_set)
        glyph_set[glyph_name].draw(recorder)
        pen = FlattenPen()
        recorder.replay(pen)
        contours = pen.finish()
        if not contours:
            raise StrokeDataError(f"字型 glyph 沒有輪廓 {character!r}: {font_path}")
        upem = int(font["head"].unitsPerEm)
        return contours, upem
    finally:
        font.close()

def is_han_character(character: str) -> bool:
    if len(character) != 1:
        return False
    value = ord(character)
    return (
        0x3400 <= value <= 0x4DBF
        or 0x4E00 <= value <= 0x9FFF
        or 0xF900 <= value <= 0xFAFF
        or 0x20000 <= value <= 0x2FA1F
    )

def transform_hanzi_point(point: tuple[float, float], origin: tuple[float, float], size: float) -> tuple[float, float]:
    """將 Make Me a Hanzi y-up 座標轉成一般畫布 y-down 座標。"""
    scale = size / HANZI_COORD_SIZE
    return (
        origin[0] + point[0] * scale,
        origin[1] + (HANZI_TOP_Y - point[1]) * scale,
    )

def transform_hanzi_contours(
    contours: Iterable[Iterable[tuple[float, float]]],
    origin: tuple[float, float],
    size: float,
) -> list[list[tuple[float, float]]]:
    return [
        [transform_hanzi_point(point, origin, size) for point in contour]
        for contour in contours
    ]

def transform_font_contours(
    contours: Iterable[Iterable[tuple[float, float]]],
    origin: tuple[float, float],
    size: float,
    upem: int,
) -> list[list[tuple[float, float]]]:
    scale = size / max(1, upem)
    # 字型座標通常以 baseline 為 y=0、向上為正；origin 是字框左上角。
    baseline = origin[1] + size * 0.88
    return [
        [(origin[0] + x * scale, baseline - y * scale) for x, y in contour]
        for contour in contours
    ]

def contours_to_mask(
    contours: Iterable[Iterable[tuple[float, float]]],
    width: int,
    height: int,
) -> np.ndarray:
    polygons: list[np.ndarray] = []
    for contour in contours:
        points = np.asarray([(round(x), round(y)) for x, y in contour], dtype=np.int32)
        if len(points) >= 3:
            polygons.append(points.reshape((-1, 1, 2)))
    mask = np.zeros((height, width), dtype=np.uint8)
    if polygons:
        # fillPoly 可一次處理複合 path；交疊/孔洞依奇偶規則填色。
        cv2.fillPoly(mask, polygons, 255, lineType=cv2.LINE_AA)
    return mask

def mask_bbox(mask: np.ndarray, padding: int = 0) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if xs.size == 0:
        return None
    height, width = mask.shape
    x0 = max(0, int(xs.min()) - padding)
    y0 = max(0, int(ys.min()) - padding)
    x1 = min(width, int(xs.max()) + 1 + padding)
    y1 = min(height, int(ys.max()) + 1 + padding)
    return x0, y0, x1, y1

def path_length(points: Iterable[tuple[float, float]]) -> float:
    source = list(points)
    return sum(math.dist(a, b) for a, b in zip(source, source[1:]))

def blend_mask(canvas_bgr: np.ndarray, mask: np.ndarray, color_bgr: tuple[int, int, int]) -> None:
    alpha = mask.astype(np.float32)[:, :, None] / 255.0
    color = np.asarray(color_bgr, dtype=np.float32).reshape(1, 1, 3)
    canvas_bgr[...] = (
        canvas_bgr.astype(np.float32) * (1.0 - alpha) + color * alpha
    ).astype(np.uint8)
