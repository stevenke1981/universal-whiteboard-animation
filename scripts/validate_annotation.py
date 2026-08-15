#!/usr/bin/env python3
"""Base annotation validation plus Chinese stroke-mask/median invariants."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from common import dump_json, load_json
from validate_annotation_base import *  # noqa: F401,F403
from validate_annotation_base import _issue, make_parser
from validate_annotation_base import validate as _base_validate


def _mask_path(element: dict, annotation_path: Path) -> Path | None:
    raw = element.get("strokeMask") or (element.get("reveal") or {}).get("maskPath")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_absolute() else (annotation_path.parent / path).resolve()


def validate(image_path: Path | None, annotation_path: Path) -> dict[str, Any]:
    report = _base_validate(image_path, annotation_path)
    data = load_json(annotation_path)
    canvas = data.get("canvas") or {}
    width, height = canvas.get("width"), canvas.get("height")
    extra: list[dict[str, Any]] = []
    for element in data.get("elements") or []:
        element_id = str(element.get("id") or "unknown")
        is_write = element.get("type") in {"text-stroke", "text-glyph"} or (element.get("reveal") or {}).get("mode") == "write"
        if not is_write:
            continue
        mask_path = _mask_path(element, annotation_path)
        if mask_path is None:
            extra.append(_issue("error", "missing-stroke-mask", "中文字逐筆元素缺少 strokeMask", element_id))
        elif not mask_path.exists():
            extra.append(_issue("error", "stroke-mask-missing", f"找不到 strokeMask: {mask_path}", element_id))
        else:
            try:
                with Image.open(mask_path) as image:
                    mask_size = image.size
                    mask_array = np.asarray(image.convert("L"))
                if isinstance(width, int) and isinstance(height, int) and mask_size != (width, height):
                    extra.append(_issue("error", "stroke-mask-size", f"strokeMask 為 {mask_size[0]}x{mask_size[1]}，canvas 為 {width}x{height}", element_id))
                if int(np.count_nonzero(mask_array)) == 0:
                    extra.append(_issue("error", "empty-stroke-mask", "strokeMask 沒有有效像素", element_id))
            except OSError as exc:
                extra.append(_issue("error", "stroke-mask-read", f"無法讀取 strokeMask: {exc}", element_id))

        points = (element.get("handPath") or {}).get("points")
        valid_points = isinstance(points, list) and len(points) >= 2 and all(
            isinstance(point, (list, tuple)) and len(point) == 2
            and all(isinstance(value, (int, float)) for value in point)
            for point in (points or [])
        )
        if not valid_points:
            extra.append(_issue("error", "invalid-stroke-median", "中文字逐筆元素需要至少兩點的 handPath.points", element_id))
        elif isinstance(width, int) and isinstance(height, int):
            if any(not (0 <= float(point[0]) < width and 0 <= float(point[1]) < height) for point in points):
                extra.append(_issue("error", "stroke-median-out-of-bounds", "handPath.points 超出 canvas", element_id))

        if element.get("strokeOrderConfidence") == "authoritative":
            if mask_path is None:
                extra.append(_issue("error", "authoritative-without-mask", "authoritative 筆畫不可缺少 mask", element_id))
            if not valid_points:
                extra.append(_issue("error", "authoritative-without-median", "authoritative 筆畫不可缺少 median", element_id))

    report["issues"].extend(extra)
    errors = [item for item in report["issues"] if item["level"] == "error"]
    warnings = [item for item in report["issues"] if item["level"] == "warning"]
    report["valid"] = not errors
    report["summary"]["errors"] = len(errors)
    report["summary"]["warnings"] = len(warnings)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if len(args.paths) == 1:
        image, annotation = None, Path(args.paths[0])
    elif len(args.paths) == 2:
        image, annotation = Path(args.paths[0]), Path(args.paths[1])
    else:
        parser.error("請傳 annotation，或 image annotation 兩個路徑")
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
    failed = not report["valid"] or (args.strict and report["summary"]["warnings"] > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
