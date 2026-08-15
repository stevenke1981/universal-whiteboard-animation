#!/usr/bin/env python3
"""依權威 strokes／medians 與獨立 stroke mask 渲染中文字。"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

from common import dump_json, load_json
from render_whiteboard_base import hex_to_bgr, imread_any, resize_aligned, transcode_h264
from chinese_render_utils import (
    ChineseFrameWriter,
    ChineseRenderConfig,
    _write_stroke,
    hand_path_points,
    load_element_mask,
)

def render(
    image_path: Path,
    annotation_path: Path,
    output_path: Path,
    cfg: ChineseRenderConfig,
    report_path: Path | None = None,
) -> dict:
    source_raw = imread_any(image_path)
    if source_raw is None:
        raise ValueError(f"無法讀取圖片: {image_path}")
    annotation = load_json(annotation_path)
    source, sx, sy = resize_aligned(source_raw, cfg.cap_long_edge)
    h, w = source.shape[:2]
    canvas = np.empty_like(source)
    canvas[...] = hex_to_bgr(annotation.get("background") or cfg.background)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = output_path.with_name(output_path.stem + "_raw.mp4")
    writer = cv2.VideoWriter(str(raw_path), cv2.VideoWriter_fourcc(*"mp4v"), cfg.fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("無法建立影片寫入器")
    fw = ChineseFrameWriter(writer, canvas)
    warnings: list[str] = []
    element_reports: list[dict] = []
    elements = sorted(annotation.get("elements") or [], key=lambda item: item.get("sequence", 10**9))
    try:
        for element in elements:
            reveal = element.get("reveal") or {}
            fw.hold_until(round(int(reveal.get("startMs", 0)) * cfg.fps / 1000))
            mask, mask_path = load_element_mask(element, annotation_path, w, h)
            points = hand_path_points(element, sx, sy, w, h)
            duration_ms = int(reveal.get("durationMs", 1))
            frames = max(1, round(duration_ms * cfg.fps / 1000))
            distance = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
            radius = max(cfg.ink_radius, int(math.ceil(float(distance.max()))) + 2)
            _write_stroke(fw, canvas, source, mask, points, frames, radius, cfg.pointer)
            element_reports.append({
                "id": element.get("id"),
                "strokeIndex": element.get("strokeIndex"),
                "mask": str(mask_path),
                "explicitMask": str(mask_path),
                "pathPoints": len(points),
                "pathSource": "handPath.points",
                "writeMode": True,
                "radius": radius,
                "frames": frames,
            })
        scene_ms = int(annotation.get("sceneDurationMs") or 0)
        final_hold_ms = int(annotation.get("finalHoldMs", 700))
        target = max(round(scene_ms * cfg.fps / 1000), fw.frames_written + max(1, round(final_hold_ms * cfg.fps / 1000)))
        fw.hold_until(target)
    finally:
        writer.release()

    final_path, codec = transcode_h264(raw_path, output_path, cfg.keep_raw)
    report = {
        "valid": True,
        "output": str(final_path),
        "codec": codec,
        "size": {"width": w, "height": h},
        "fps": cfg.fps,
        "frames": fw.frames_written,
        "elements": element_reports,
        "warnings": warnings,
    }
    if report_path:
        dump_json(report, report_path)
    return report

def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="依權威筆順資料逐筆書寫中文字")
    parser.add_argument("image")
    parser.add_argument("annotation")
    parser.add_argument("output")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--cap-long-edge", type=int, default=1080)
    parser.add_argument("--pointer", choices=["pen", "circle", "none"], default="pen")
    parser.add_argument("--ink-radius", type=int, default=5)
    parser.add_argument("--background", default="#F5EBD7")
    parser.add_argument("--report")
    parser.add_argument("--keep-raw", action="store_true")
    # 與一般渲染器相容；中文字 write 模式不重新推導路徑或切 ink/color。
    parser.add_argument("--ink-path", choices=["grid", "skeleton"], default="skeleton")
    parser.add_argument("--color-fill", choices=["wipe", "brush"], default="wipe")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    cfg = ChineseRenderConfig(
        fps=max(1, args.fps),
        cap_long_edge=max(2, args.cap_long_edge),
        pointer=args.pointer,
        ink_radius=max(1, args.ink_radius),
        background=args.background,
        keep_raw=args.keep_raw,
    )
    try:
        report = render(
            Path(args.image), Path(args.annotation), Path(args.output), cfg,
            Path(args.report) if args.report else None,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    print(f"OUTPUT={Path(report['output']).resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
