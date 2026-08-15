#!/usr/bin/env python3
"""中文字逐筆場景與 annotation 產生器。"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from chinese_stroke_data import (
    CharacterStrokeData,
    StrokeDataError,
    StrokeDataRepository,
    blend_mask,
    contours_to_mask,
    font_glyph_contours,
    is_han_character,
    mask_bbox,
    parse_svg_contours,
    transform_font_contours,
    transform_hanzi_contours,
    transform_hanzi_point,
)
from chinese_stroke_layout import (
    STROKE_ORDER_RULES,
    _duration_ms,
)
from chinese_stroke_layout import (
    _hex_to_bgr,
    _new_element,
    _relative_posix,
    _save_mask,
    find_default_font,
    plan_layout,
    stroke_key,
)

SKILL_ROOT = Path(__file__).resolve().parent.parent


def _authoritative_strokes(
    data: CharacterStrokeData,
    *,
    origin: tuple[float, float],
    size: int,
    width: int,
    height: int,
) -> list[tuple[np.ndarray, list[tuple[float, float]]]]:
    result: list[tuple[np.ndarray, list[tuple[float, float]]]] = []
    for path_data, median_data in zip(data.strokes, data.medians):
        raw_contours = parse_svg_contours(path_data)
        contours = transform_hanzi_contours(raw_contours, origin, size)
        mask = contours_to_mask(contours, width, height)
        median = [transform_hanzi_point(point, origin, size) for point in median_data]
        result.append((mask, median))
    return result


def _font_glyph_mask(
    character: str,
    font_path: str,
    *,
    origin: tuple[float, float],
    size: int,
    width: int,
    height: int,
) -> np.ndarray:
    contours, upem = font_glyph_contours(font_path, character)
    transformed = transform_font_contours(contours, origin, size, upem)
    return contours_to_mask(transformed, width, height)


def _font_heuristic_masks(
    character: str,
    font_path: str,
    *,
    origin: tuple[float, float],
    size: int,
    width: int,
    height: int,
) -> list[np.ndarray]:
    contours, upem = font_glyph_contours(font_path, character)
    transformed = transform_font_contours(contours, origin, size, upem)
    ranked = sorted(
        transformed,
        key=lambda contour: stroke_key(
            (
                min(point[0] for point in contour),
                min(point[1] for point in contour),
                max(point[0] for point in contour),
                max(point[1] for point in contour),
            ),
            size,
        ),
    )
    return [contours_to_mask([contour], width, height) for contour in ranked]


def split_scene(
    *,
    text: str,
    font_path: str | None = None,
    size: int,
    width: int,
    height: int,
    bg: str,
    ink: str,
    padding: int,
    base_ms: int,
    ms_per_px: float,
    final_hold_ms: int = 700,
    scene_id: str = "scene-01",
    out_dir: str | Path = ".",
    stroke_data: str | Path | None = None,
    stroke_source: str = "auto",
    strict_stroke_order: bool = False,
    min_stroke_ms: int = 220,
    max_stroke_ms: int = 950,
    char_gap: float = 0.0,
) -> dict[str, Any]:
    """拆成逐筆 mask、產生場景圖與可直接渲染的 annotation。"""
    if not text:
        raise ValueError("text 不可為空")
    if stroke_source not in {"auto", "data", "font-glyph", "font-heuristic"}:
        raise ValueError(f"未知 stroke_source: {stroke_source}")
    if strict_stroke_order:
        stroke_source = "data"

    out_root = Path(out_dir).expanduser().resolve()
    scenes_dir = out_root / "scenes"
    strokes_dir = out_root / "build" / "strokes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    strokes_dir.mkdir(parents=True, exist_ok=True)
    scene_path = scenes_dir / f"{scene_id}.png"
    annotation_path = scenes_dir / f"{scene_id}.annotation.json"

    resolved_font = Path(font_path).expanduser().resolve() if font_path else find_default_font()
    data_path = Path(stroke_data).expanduser().resolve() if stroke_data else StrokeDataRepository.discover(
        out_root, SKILL_ROOT
    )
    repository = StrokeDataRepository(data_path)
    origins = plan_layout(text, str(resolved_font) if resolved_font else None, size, width, height, char_gap)

    background_bgr = _hex_to_bgr(bg)
    ink_bgr = _hex_to_bgr(ink)
    canvas = np.empty((height, width, 3), dtype=np.uint8)
    canvas[...] = background_bgr

    elements: list[dict[str, Any]] = []
    warnings: list[str] = []
    per_position: list[dict[str, Any]] = []
    start_ms = 0
    sequence = 0

    for char_index, character in enumerate(text):
        if character.isspace():
            per_position.append({"index": char_index + 1, "character": character, "strokes": 0, "source": "space"})
            continue

        origin = origins[char_index]
        data: CharacterStrokeData | None = None
        if is_han_character(character) and stroke_source in {"auto", "data"}:
            data = repository.get(character)

        if data is not None:
            strokes = _authoritative_strokes(
                data,
                origin=origin,
                size=size,
                width=width,
                height=height,
            )
            char_source = "authoritative-stroke-data"
            confidence = "authoritative"
            for stroke_index, (mask, median) in enumerate(strokes, start=1):
                bbox = mask_bbox(mask, padding)
                if bbox is None:
                    raise StrokeDataError(f"{character!r} 第 {stroke_index} 筆 mask 為空")
                sequence += 1
                mask_file = strokes_dir / f"{scene_id}-stroke-{sequence:03d}.png"
                _save_mask(mask, mask_file)
                blend_mask(canvas, mask, ink_bgr)
                duration = _duration_ms(
                    median,
                    base_ms=base_ms,
                    ms_per_px=ms_per_px,
                    min_ms=min_stroke_ms,
                    max_ms=max_stroke_ms,
                )
                elements.append(
                    _new_element(
                        sequence=sequence,
                        char_index=char_index,
                        character=character,
                        stroke_index=stroke_index,
                        stroke_count=len(strokes),
                        region=bbox,
                        start_ms=start_ms,
                        duration_ms=duration,
                        mask_path=_relative_posix(mask_file, annotation_path.parent),
                        source=char_source,
                        confidence=confidence,
                        median=median,
                        text=text,
                    )
                )
                start_ms += duration
            per_position.append(
                {
                    "index": char_index + 1,
                    "character": character,
                    "strokes": len(strokes),
                    "source": char_source,
                    "confidence": confidence,
                }
            )
            continue

        if is_han_character(character) and stroke_source == "data":
            source_text = str(data_path) if data_path else "未指定"
            raise StrokeDataError(
                f"缺少 {character!r} 的權威筆畫資料（source={source_text}）。"
                "請提供 Hanzi Writer Data 目錄或 Make Me a Hanzi graphics.txt。"
            )
        if resolved_font is None:
            raise ValueError(
                f"{character!r} 需要字型 fallback，但未找到中文字型；請傳 --font 或設定 WHITEBOARD_FONT"
            )

        if stroke_source == "font-heuristic":
            masks = _font_heuristic_masks(
                character,
                str(resolved_font),
                origin=origin,
                size=size,
                width=width,
                height=height,
            )
            char_source = "font-outline-heuristic"
            element_type = "text-stroke"
        else:
            masks = [
                _font_glyph_mask(
                    character,
                    str(resolved_font),
                    origin=origin,
                    size=size,
                    width=width,
                    height=height,
                )
            ]
            char_source = "font-glyph-fallback"
            element_type = "text-glyph"
        confidence = "approximate"
        warnings.append(
            f"{character!r} 沒有使用權威筆畫資料，已採 {char_source}；不可視為正確筆順。"
        )
        non_empty_masks = [mask for mask in masks if mask_bbox(mask) is not None]
        if not non_empty_masks:
            raise StrokeDataError(f"字型無法產生 {character!r} 的可見 glyph")
        for stroke_index, mask in enumerate(non_empty_masks, start=1):
            bbox = mask_bbox(mask, padding)
            assert bbox is not None
            sequence += 1
            mask_file = strokes_dir / f"{scene_id}-stroke-{sequence:03d}.png"
            _save_mask(mask, mask_file)
            blend_mask(canvas, mask, ink_bgr)
            x0, y0, x1, y1 = bbox
            approximate_path = [(x0, (y0 + y1) / 2), (x1, (y0 + y1) / 2)]
            duration = _duration_ms(
                approximate_path,
                base_ms=base_ms,
                ms_per_px=ms_per_px,
                min_ms=min_stroke_ms,
                max_ms=max_stroke_ms,
            )
            elements.append(
                _new_element(
                    sequence=sequence,
                    char_index=char_index,
                    character=character,
                    stroke_index=stroke_index,
                    stroke_count=len(non_empty_masks),
                    region=bbox,
                    start_ms=start_ms,
                    duration_ms=duration,
                    mask_path=_relative_posix(mask_file, annotation_path.parent),
                    source=char_source,
                    confidence=confidence,
                    median=None,
                    text=text,
                    element_type=element_type,
                )
            )
            start_ms += duration
        per_position.append(
            {
                "index": char_index + 1,
                "character": character,
                "strokes": len(non_empty_masks),
                "source": char_source,
                "confidence": confidence,
            }
        )

    if not elements:
        raise ValueError("文字沒有產生任何可繪製元素")

    Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)).save(scene_path)
    scene_duration = start_ms + final_hold_ms
    annotation: dict[str, Any] = {
        "version": 1,
        "sceneId": scene_id,
        "canvas": {"width": width, "height": height},
        "background": bg,
        "storyBasis": text,
        "coreMessage": text,
        "sceneDurationMs": scene_duration,
        "finalHoldMs": final_hold_ms,
        "strokeOrderRules": STROKE_ORDER_RULES,
        "writingSystem": {
            "script": "Han",
            "layout": "horizontal-ltr",
            "characterPolicy": "exact-unicode-no-auto-conversion",
            "strokeOrder": "data-array-order",
            "strokeDirection": "median-start-to-end",
            "compoundStrokePolicy": "single-element-no-pen-lift",
            "intersectionPolicy": "per-stroke-explicit-mask",
            "fallbackPolicy": stroke_source,
        },
        "strokeDataSource": str(data_path) if data_path else None,
        "warnings": warnings,
        "elements": elements,
    }
    annotation_path.write_text(
        json.dumps(annotation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    aggregate = Counter()
    for item in per_position:
        aggregate[item["character"]] += item["strokes"]
    return {
        "sceneImage": str(scene_path),
        "annotation": str(annotation_path),
        "chars": len(text),
        "strokes": len(elements),
        "perChar": dict(aggregate),
        "perPosition": per_position,
        "sceneDurationMs": scene_duration,
        "strokeDataSource": str(data_path) if data_path else None,
        "authoritative": bool(
            han_items := [item for item in per_position if is_han_character(item["character"])]
        ) and all(item.get("confidence") == "authoritative" for item in han_items),
        "warnings": warnings,
        "rules": STROKE_ORDER_RULES,
    }
