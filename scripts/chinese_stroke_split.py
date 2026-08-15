#!/usr/bin/env python3
"""將中文文字轉成符合資料筆順與書寫方向的白板動畫場景。"""
from __future__ import annotations

import argparse
import json
import sys

from chinese_stroke_data import StrokeDataError
from chinese_stroke_layout import STROKE_ORDER_RULES, decompose_contours, find_default_font, plan_layout, stroke_key
from chinese_stroke_scene import split_scene

def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--text", default="日日是好日！")
    parser.add_argument("--font", help="fallback 字型；未指定時自動偵測")
    parser.add_argument(
        "--stroke-data",
        help="Hanzi Writer Data 目錄、逐字 JSON、或 Make Me a Hanzi graphics.txt/JSONL",
    )
    parser.add_argument(
        "--stroke-source",
        choices=["auto", "data", "font-glyph", "font-heuristic"],
        default="auto",
        help="data=缺字即失敗；auto=資料優先後 fallback；font-heuristic=舊輪廓近似",
    )
    parser.add_argument(
        "--strict-stroke-order",
        action="store_true",
        help="等同 --stroke-source data；所有漢字都必須有權威 strokes/medians",
    )
    parser.add_argument("--size", type=int, default=250)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--bg", default="#F5EBD7")
    parser.add_argument("--ink", default="#373737")
    parser.add_argument("--padding", type=int, default=14)
    parser.add_argument("--base-ms", type=int, default=280)
    parser.add_argument("--ms-per-px", type=float, default=0.42)
    parser.add_argument("--min-stroke-ms", type=int, default=220)
    parser.add_argument("--max-stroke-ms", type=int, default=950)
    parser.add_argument("--final-hold-ms", type=int, default=700)
    parser.add_argument("--char-gap", type=float, default=0.0)
    parser.add_argument("--scene-id", default="scene-01")
    parser.add_argument("--out-dir", default=".")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    try:
        summary = split_scene(
            text=args.text,
            font_path=args.font,
            size=max(16, args.size),
            width=max(64, args.width),
            height=max(64, args.height),
            bg=args.bg,
            ink=args.ink,
            padding=max(0, args.padding),
            base_ms=max(0, args.base_ms),
            ms_per_px=max(0.0, args.ms_per_px),
            final_hold_ms=max(0, args.final_hold_ms),
            scene_id=args.scene_id,
            out_dir=args.out_dir,
            stroke_data=args.stroke_data,
            stroke_source=args.stroke_source,
            strict_stroke_order=args.strict_stroke_order,
            min_stroke_ms=max(1, args.min_stroke_ms),
            max_stroke_ms=max(args.min_stroke_ms, args.max_stroke_ms),
            char_gap=args.char_gap,
        )
    except (OSError, ValueError, StrokeDataError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

__all__ = [
    "STROKE_ORDER_RULES", "decompose_contours", "find_default_font", "plan_layout", "split_scene", "stroke_key"
]

if __name__ == "__main__":
    raise SystemExit(main())
