#!/usr/bin/env python3
"""輕量 selftest：給 Hermes 安裝後驗證模組與熱路徑。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from chinese_stroke_split import clamp_region, contour_centerline
    from render_whiteboard import hand_path_from_element
    from run_pipeline import discover_font

    region = clamp_region(-4, -4, 700, 400, 640, 360, 8)
    assert region["x"] >= 0 and region["y"] >= 0
    assert region["x"] + region["width"] <= 640

    line = contour_centerline([(0, 0), (80, 0), (80, 10), (0, 10)], True)
    assert len(line) >= 2
    assert line[0][0] < line[-1][0]

    points, lifts = hand_path_from_element(
        {"handPath": {"points": [[0, 0], [30, 0], [60, 1]]}},
        1.0,
        1.0,
    )
    assert lifts == set()
    assert points[0] == (0, 0) and points[-1][0] >= 60

    try:
        font = discover_font(None)
        print(f"[ok] font={font}")
    except FileNotFoundError as exc:
        print(f"[warn] {exc}")

    print("[ok] selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
