#!/usr/bin/env python3
"""驗證白板動畫 annotation JSON 的 Schema、座標、時序與遮罩風險。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from common import dump_json, load_json

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = SKILL_ROOT / "schemas" / "annotation.schema.json"


def _issue(level: str, code: str, message: str, element_id: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"level": level, "code": code, "message": message}
    if element_id:
        item["elementId"] = element_id
    return item


def _region_in_bounds(region: dict, width: int, height: int) -> bool:
    return (
        isinstance(region.get("x"), int)
        and isinstance(region.get("y"), int)
        and isinstance(region.get("width"), int)
        and isinstance(region.get("height"), int)
        and region["x"] >= 0
        and region["y"] >= 0
        and region["width"] > 0
        and region["height"] > 0
        and region["x"] + region["width"] <= width
        and region["y"] + region["height"] <= height
    )


def _scaled_mask(width: int, height: int, region: dict, max_edge: int = 1200) -> tuple[np.ndarray, float, float]:
    scale = min(1.0, max_edge / max(width, height))
    sw = max(1, int(round(width * scale)))
    sh = max(1, int(round(height * scale)))
    sx, sy = sw / width, sh / height
    mask = np.zeros((sh, sw), dtype=bool)
    x0 = max(0, min(sw, int(round(region["x"] * sx))))
    y0 = max(0, min(sh, int(round(region["y"] * sy))))
    x1 = max(0, min(sw, int(round((region["x"] + region["width"]) * sx))))
    y1 = max(0, min(sh, int(round((region["y"] + region["height"]) * sy))))
    mask[y0:y1, x0:x1] = True
    return mask, sx, sy


def _paint_region(mask: np.ndarray, region: dict, sx: float, sy: float, value: bool) -> None:
    h, w = mask.shape
    x0 = max(0, min(w, int(round(region["x"] * sx))))
    y0 = max(0, min(h, int(round(region["y"] * sy))))
    x1 = max(0, min(w, int(round((region["x"] + region["width"]) * sx))))
    y1 = max(0, min(h, int(round((region["y"] + region["height"]) * sy))))
    mask[y0:y1, x0:x1] = value


def validate(image_path: Path | None, annotation_path: Path) -> dict[str, Any]:
    data = load_json(annotation_path)
    issues: list[dict[str, Any]] = []

    if jsonschema is not None:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
            location = ".".join(str(part) for part in error.path) or "root"
            issues.append(_issue("error", "schema", f"{location}: {error.message}"))
    else:
        issues.append(_issue("warning", "jsonschema-missing", "未安裝 jsonschema，已略過正式 Schema 驗證"))

    canvas = data.get("canvas") or {}
    width = canvas.get("width")
    height = canvas.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        width = height = 0
        issues.append(_issue("error", "invalid-canvas", "canvas.width/height 必須是正整數"))

    if image_path is not None:
        try:
            with Image.open(image_path) as image:
                iw, ih = image.size
            if (iw, ih) != (width, height):
                issues.append(
                    _issue(
                        "error",
                        "canvas-image-mismatch",
                        f"圖片為 {iw}x{ih}，annotation canvas 為 {width}x{height}",
                    )
                )
        except OSError as exc:
            issues.append(_issue("error", "image-read-failed", f"無法讀取圖片: {exc}"))

    elements = data.get("elements") or []
    ids = [str(element.get("id", "")) for element in elements]
    duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
    if duplicate_ids:
        issues.append(_issue("error", "duplicate-id", f"重複 element id: {', '.join(duplicate_ids)}"))

    sequences = [element.get("sequence") for element in elements]
    expected = list(range(1, len(elements) + 1))
    if sorted(value for value in sequences if isinstance(value, int)) != expected:
        issues.append(_issue("error", "sequence-gap", f"sequence 必須連續為 {expected}"))

    scene_duration = data.get("sceneDurationMs", 0)
    final_hold = data.get("finalHoldMs", 700)
    last_end = 0
    intervals: list[tuple[int, int, str]] = []
    sorted_elements = sorted(elements, key=lambda item: item.get("sequence", 10**9))

    for index, element in enumerate(sorted_elements):
        element_id = str(element.get("id") or f"index-{index}")
        region = element.get("region") or {}
        if width and height and not _region_in_bounds(region, width, height):
            issues.append(_issue("error", "region-out-of-bounds", f"region 越界或不是整數正尺寸: {region}", element_id))
        reveal = element.get("reveal") or {}
        start = reveal.get("startMs")
        duration = reveal.get("durationMs")
        if not isinstance(start, int) or start < 0:
            issues.append(_issue("error", "invalid-start", "startMs 必須是非負整數", element_id))
            continue
        if not isinstance(duration, int) or duration <= 0:
            issues.append(_issue("error", "invalid-duration", "durationMs 必須是正整數", element_id))
            continue
        end = start + duration
        last_end = max(last_end, end)
        intervals.append((start, end, element_id))
        if isinstance(scene_duration, int) and end > scene_duration:
            issues.append(
                _issue(
                    "error",
                    "element-exceeds-scene",
                    f"元素結束 {end}ms 超過 sceneDurationMs={scene_duration}",
                    element_id,
                )
            )
        if not element.get("subtitle"):
            issues.append(_issue("warning", "missing-subtitle", "元素沒有 subtitle 對應", element_id))
        if not element.get("narrativeRole"):
            issues.append(_issue("warning", "missing-narrative-role", "元素沒有 narrativeRole", element_id))
        for protected in reveal.get("protectedRegions", []) or []:
            if width and height and not _region_in_bounds(protected, width, height):
                issues.append(
                    _issue("error", "protected-region-out-of-bounds", f"protectedRegions 越界: {protected}", element_id)
                )

        if width and height and _region_in_bounds(region, width, height):
            mask, sx, sy = _scaled_mask(width, height, region)
            original_area = int(mask.sum())
            policy = element.get("maskPolicy", "subtract-later")
            if policy == "subtract-later":
                for later in sorted_elements[index + 1 :]:
                    later_region = later.get("region") or {}
                    if _region_in_bounds(later_region, width, height):
                        _paint_region(mask, later_region, sx, sy, False)
            if policy in ("subtract-later", "explicit"):
                for protected in reveal.get("protectedRegions", []) or []:
                    if _region_in_bounds(protected, width, height):
                        _paint_region(mask, protected, sx, sy, False)
            remaining = int(mask.sum())
            removed_ratio = 1.0 - remaining / max(1, original_area)
            if removed_ratio >= 0.8:
                issues.append(
                    _issue(
                        "warning",
                        "over-masked",
                        f"允許遮罩被扣除 {removed_ratio:.0%}；考慮 explicit 或縮小後續 region",
                        element_id,
                    )
                )
            if remaining == 0:
                issues.append(_issue("error", "empty-mask", "元素允許遮罩為空", element_id))

    intervals.sort()
    for (start_a, end_a, id_a), (start_b, end_b, id_b) in zip(intervals, intervals[1:]):
        if start_b < end_a:
            issues.append(
                _issue(
                    "warning",
                    "timeline-overlap",
                    f"{id_a} 與 {id_b} 時間重疊 {end_a - start_b}ms；單筆模式通常應串行",
                )
            )

    if isinstance(scene_duration, int) and isinstance(final_hold, int):
        actual_hold = scene_duration - last_end
        if actual_hold < final_hold:
            issues.append(
                _issue(
                    "error",
                    "insufficient-final-hold",
                    f"結尾停留只有 {actual_hold}ms，要求至少 {final_hold}ms",
                )
            )

    errors = [item for item in issues if item["level"] == "error"]
    warnings = [item for item in issues if item["level"] == "warning"]
    return {
        "valid": not errors,
        "annotation": str(annotation_path),
        "image": str(image_path) if image_path else None,
        "summary": {
            "errors": len(errors),
            "warnings": len(warnings),
            "elements": len(elements),
            "sceneDurationMs": scene_duration,
            "lastElementEndMs": last_end,
        },
        "issues": issues,
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="驗證白板動畫 annotation；可傳 annotation，或 image annotation"
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="annotation.json，或『場景圖片 annotation.json』",
    )
    parser.add_argument("--report", help="JSON 報告輸出")
    parser.add_argument("--strict", action="store_true", help="有 warning 也回傳失敗")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    if len(args.paths) == 1:
        image = None
        annotation = Path(args.paths[0])
    elif len(args.paths) == 2:
        image = Path(args.paths[0])
        annotation = Path(args.paths[1])
    else:
        make_parser().error("請傳 annotation，或 image annotation 兩個路徑")
    try:
        report = validate(image, annotation)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if args.report:
        dump_json(report, args.report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    for item in report["issues"]:
        suffix = f" ({item.get('elementId')})" if item.get("elementId") else ""
        print(f"[{item['level']}] {item['code']}{suffix}: {item['message']}")
    print(f"VALID={str(report['valid']).lower()}")
    if not report["valid"]:
        return 1
    if args.strict and report["summary"]["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
