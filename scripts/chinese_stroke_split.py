#!/usr/bin/env python3
"""中文字逐筆畫白板拆分器（筆順邏輯版）。

以字型輪廓（fontTools 讀 TTF/OTC glyph outline）將中文字拆成「筆畫組」，
依漢字筆順口訣排序後輸出逐筆手繪的 annotation：

    從左到右，從上到下。
    先橫後豎，先撇後捺。
    橫豎相交，先橫後豎。
    左右結構，先左後右。
    上下結構，先上後下。

實作近似規則：
- 全句字序：由左至右（字元 advance）。
- 單字內：先「上→下」分層（min_y），同層內「橫向筆畫優先、再左→右」。
- 每「筆畫組」＝glyph 輪廓的單一封閉 sub-path（composite 字形已遞迴展開）。
  註：楷體中相連筆畫（如「日」外框）會合併為一個輪廓，屬可接受的手寫近似。

輸出：
- scenes/<scene-id>.png          逐筆疊加的場景圖（同 PIL 渲染結果）
- scenes/<scene-id>.annotation.json  每筆一個 element（reveal 依筆順）
- build/strokes/<scene-id>-stroke-<n>.png  每筆 mask（檢查用）

範例：
    python scripts/chinese_stroke_split.py \
      --text "日日是好日！" --font C:/Windows/Fonts/kaiu.ttf \
      --size 250 --width 1920 --height 1080 --scene-id scene-01
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from functools import lru_cache
from pathlib import Path

import freetype
from PIL import Image, ImageDraw, ImageFont

DEFAULT_FONT = "C:/Windows/Fonts/kaiu.ttf"

# 筆順口訣（紀錄於 SKILL.md）
STROKE_ORDER_RULES = (
    "從左到右，從上到下；先橫後豎，先撇後捺；橫豎相交，先橫後豎；"
    "左右結構，先左後右；上下結構，先上後下。"
)


def _cubic_curve(pts, steps: int = 16) -> list[tuple[float, float]]:
    """貝塞爾曲線取樣：pts = [p0, c1, c2, p1]。"""
    (p0x, p0y), (c1x, c1y), (c2x, c2y), (p1x, p1y) = pts
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**3 * p0x + 3 * mt**2 * t * c1x + 3 * mt * t**2 * c2x + t**3 * p1x
        y = mt**3 * p0y + 3 * mt**2 * t * c1y + 3 * mt * t**2 * c2y + t**3 * p1y
        out.append((x, y))
    return out


def _quad_curve(pts, steps: int = 12) -> list[tuple[float, float]]:
    """二次貝塞爾取樣：pts = [p0, c, p1]。"""
    (p0x, p0y), (cx, cy), (p1x, p1y) = pts
    out = []
    for i in range(1, steps + 1):
        t = i / steps
        mt = 1 - t
        x = mt**2 * p0x + 2 * mt * t * cx + t**2 * p1x
        y = mt**2 * p0y + 2 * mt * t * cy + t**2 * p1y
        out.append((x, y))
    return out


@lru_cache(maxsize=8)
def _load_face(font_path: str) -> freetype.Face:
    return freetype.Face(font_path)


def decompose_contours(font_path: str, char: str, pixel_size: float,
                       origin: tuple[float, float] | float,
                       extra: tuple[float, float] | None = None,
                       ) -> list[list[tuple[float, float]]]:
    """展開字元輪廓到畫布像素。

    新呼叫：decompose_contours(font, char, pixel_size, (pen_x, baseline_y))
    舊呼叫：decompose_contours(font, char, upem, scale, origin)
    使用 set_pixel_sizes，避免 FT_LOAD_NO_SCALE 把楷體複合字拆歪。
    """
    if extra is not None:
        pixel_size = float(pixel_size) * float(origin)  # type: ignore[arg-type]
        origin = extra
    pen_x, baseline_y = origin  # type: ignore[misc]
    face = _load_face(font_path)
    face.set_pixel_sizes(0, max(1, int(round(float(pixel_size)))))
    face.load_char(char, freetype.FT_LOAD_NO_BITMAP | freetype.FT_LOAD_NO_HINTING)
    outline = face.glyph.outline
    scale = 1.0 / 64.0
    contours: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []

    def _flush() -> None:
        if len(current) >= 3:
            contours.append(list(current))
        current.clear()

    def _to_px(p) -> tuple[float, float]:
        return (pen_x + p.x * scale, baseline_y - p.y * scale)

    def move(control, _ctx) -> None:
        _flush()
        current.append(_to_px(control))

    def line(control, _ctx) -> None:
        current.append(_to_px(control))

    def quad(control, to, _ctx) -> None:
        current.extend(_quad_curve([current[-1], _to_px(control), _to_px(to)]))

    def cubic(c1, c2, to, _ctx) -> None:
        current.extend(_cubic_curve([current[-1], _to_px(c1), _to_px(c2), _to_px(to)]))

    outline.decompose(None, move, line, quad, cubic)
    _flush()
    return contours


def signed_area(pts: list[tuple[float, float]]) -> float:
    total = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        total += x1 * y2 - x2 * y1
    return total / 2.0


def ink_contours(contours: list[list[tuple[float, float]]], min_area: float = 12.0) -> tuple[list, list]:
    """分開實心筆畫與孔洞；孔洞不單獨當一筆。"""
    usable = [c for c in contours if abs(signed_area(c)) >= min_area]
    if not usable:
        return [], []
    areas = [signed_area(c) for c in usable]
    sign = 1.0 if max(areas, key=abs) > 0 else -1.0
    ink = [c for c, area in zip(usable, areas) if area * sign > 0]
    holes = [c for c, area in zip(usable, areas) if area * sign < 0]
    return ink, holes


def stroke_key(bbox: tuple[float, float, float, float], char_height: float):
    """筆順排序鍵（口訣近似）。"""
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    layer = int(y0 / max(1.0, char_height * 0.34))  # 上→下分層
    horizontal_first = 0 if w >= h else 1            # 先橫後豎
    return (layer, horizontal_first, x0)


def plan_layout(text: str, font_path: str, size: int, width: int, height: int,
                char_gap: float = 0.0) -> list[tuple[float, float]]:
    """回傳每字的 pen 位置（x, baseline）。整句水平置中。"""
    img_font = ImageFont.truetype(font_path, size)
    ascent, descent = img_font.getmetrics()
    total = sum(img_font.getlength(ch) for ch in text) + char_gap * max(0, len(text) - 1)
    x = (width - total) / 2.0
    y_top = (height - (ascent + descent)) / 2.0
    baseline = y_top + ascent
    origins = []
    for ch in text:
        origins.append((x, baseline))
        x += img_font.getlength(ch) + char_gap
    return origins


def _round_point(point: tuple[float, float]) -> list[float]:
    return [round(float(point[0]), 2), round(float(point[1]), 2)]


def contour_centerline(pts: list[tuple[float, float]], horizontal: bool) -> list[list[float]]:
    """沿筆畫長軸取掃描線質心，作為書寫中線。"""
    if len(pts) < 3:
        return [_round_point(p) for p in pts]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0 = math.floor(min(xs)), math.floor(min(ys))
    x1, y1 = math.ceil(max(xs)), math.ceil(max(ys))
    width = max(1, x1 - x0 + 1)
    height = max(1, y1 - y0 + 1)
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon([(round(x - x0), round(y - y0)) for x, y in pts], fill=1)
    pixels = image.load()
    raw: list[list[float]] = []
    if horizontal:
        for x in range(width):
            hits = [y for y in range(height) if pixels[x, y]]
            if hits:
                raw.append([x0 + x, y0 + (sum(hits) / len(hits))])
    else:
        for y in range(height):
            hits = [x for x in range(width) if pixels[x, y]]
            if hits:
                raw.append([x0 + (sum(hits) / len(hits)), y0 + y])
    if len(raw) < 2:
        return [_round_point(pts[0]), _round_point(pts[len(pts) // 2])]
    step = max(1, len(raw) // 80)
    sampled = raw[::step]
    if sampled[-1] != raw[-1]:
        sampled.append(raw[-1])
    return [_round_point((x, y)) for x, y in sampled]


def build_hand_path(pts: list[tuple[float, float]], horizontal: bool) -> dict:
    contour = [_round_point(p) for p in pts]
    points = contour_centerline(pts, horizontal)
    return {
        "kind": "stroke-centerline",
        "easing": "easeInOut",
        "contour": contour,
        "points": points,
        "start": points[0],
        "end": points[-1],
    }


def clamp_region(x0: float, y0: float, x1: float, y1: float, width: int, height: int, padding: int) -> dict:
    x = max(0, int(x0) - padding)
    y = max(0, int(y0) - padding)
    right = min(width, int(math.ceil(x1)) + padding)
    bottom = min(height, int(math.ceil(y1)) + padding)
    return {
        "x": x,
        "y": y,
        "width": max(1, right - x),
        "height": max(1, bottom - y),
    }


def _save_stroke_preview(path: Path, pts: list[tuple[float, float]], ink: str, bg: str, padding: int = 8) -> None:
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w = max(1, int(math.ceil(x1 - x0)) + padding * 2)
    h = max(1, int(math.ceil(y1 - y0)) + padding * 2)
    image = Image.new("RGB", (w, h), bg)
    shifted = [(round(x - x0 + padding), round(y - y0 + padding)) for x, y in pts]
    ImageDraw.Draw(image).polygon(shifted, fill=ink)
    image.save(path)


def split_scene(*, text: str, font_path: str, size: int, width: int, height: int,
                bg: str, ink: str, padding: int, base_ms: int, ms_per_px: float,
                final_hold_ms: int = 700, scene_id: str = "scene-01",
                out_dir: str | Path = ".", write_stroke_previews: bool = True) -> dict:
    """主流程：拆筆畫 → 排序 → 疊加場景圖 → annotation JSON。回傳摘要 dict。"""
    origins = plan_layout(text, font_path, size, width, height)

    image = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(image)
    elements: list[dict] = []
    seq = 0
    start_ms = 0
    build_strokes = Path(out_dir) / "build" / "strokes"
    build_strokes.mkdir(parents=True, exist_ok=True)

    # 第一遍：拆全部輪廓，計算整句墨水 bbox 做垂直置中
    all_contours: list[list[list[tuple[float, float]]]] = []
    for ci, ch in enumerate(text):
        contours = decompose_contours(font_path, ch, size, origins[ci])
        if not contours:
            raise ValueError(f"拆不到輪廓: {ch!r}")
        all_contours.append(contours)
    all_pts = [p for cs in all_contours for c in cs for p in c]
    if all_pts:
        ink_min_y = min(p[1] for p in all_pts)
        ink_max_y = max(p[1] for p in all_pts)
        dy = (height - (ink_min_y + ink_max_y)) / 2.0
        all_contours = [[[(x, y + dy) for x, y in c] for c in cs] for cs in all_contours]

    for ci, ch in enumerate(text):
        ink_cs, holes = ink_contours(all_contours[ci])
        if not ink_cs:
            raise ValueError(f"拆不到實心筆畫: {ch!r}")
        char_height = size * 0.95
        sorted_contours = sorted(enumerate(ink_cs), key=lambda it: stroke_key(
            (min(p[0] for p in it[1]), min(p[1] for p in it[1]),
             max(p[0] for p in it[1]), max(p[1] for p in it[1])), char_height))

        for rank, (orig_idx, pts) in enumerate(sorted_contours):
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
            w, h = x1 - x0, y1 - y0
            horizontal = w >= h
            duration = max(220, min(950, int(base_ms + (w + h) * ms_per_px)))
            draw.polygon([(round(x), round(y)) for x, y in pts], fill=ink)
            if write_stroke_previews:
                _save_stroke_preview(build_strokes / f"{scene_id}-stroke-{seq + 1:02d}.png", pts, ink, bg)

            seq += 1
            elements.append({
                "id": f"char-{ci + 1}-stroke-{rank + 1}",
                "label": f"第 {ci + 1} 字 筆畫 {rank + 1}：{ch}",
                "sequence": seq,
                "type": "text-stroke",
                "narrativeRole": "中文字筆順書寫",
                "subtitle": text,
                "subjectIds": [],
                "maskPolicy": "explicit",
                "region": clamp_region(x0, y0, x1, y1, width, height, padding),
                "handPath": build_hand_path(pts, horizontal),
                "reveal": {
                    "direction": "left_to_right" if horizontal else "top_to_bottom",
                    "startMs": start_ms,
                    "durationMs": duration,
                    "protectedRegions": [],
                },
            })
            start_ms += duration
        for hole in holes:
            draw.polygon([(round(x), round(y)) for x, y in hole], fill=bg)

    scene_duration = start_ms + final_hold_ms
    scene_path = Path(out_dir) / "scenes" / f"{scene_id}.png"
    scene_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(scene_path)

    annotation = {
        "version": 1,
        "sceneId": scene_id,
        "canvas": {"width": width, "height": height},
        "background": bg,
        "storyBasis": text,
        "coreMessage": text,
        "strokeOrderRules": STROKE_ORDER_RULES,
        "sceneDurationMs": scene_duration,
        "finalHoldMs": final_hold_ms,
        "elements": elements,
    }
    ann_path = Path(out_dir) / "scenes" / f"{scene_id}.annotation.json"
    ann_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "sceneImage": str(scene_path),
        "annotation": str(ann_path),
        "chars": len(text),
        "strokes": seq,
        "perChar": {ch: sum(1 for e in elements if e["label"].startswith(f"第 {i + 1} 字"))
                    for i, ch in enumerate(text)},
        "sceneDurationMs": scene_duration,
        "rules": STROKE_ORDER_RULES,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text", default="日日是好日！")
    ap.add_argument("--font", default=DEFAULT_FONT)
    ap.add_argument("--size", type=int, default=250)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--bg", default="#F5EBD7")
    ap.add_argument("--ink", default="#373737")
    ap.add_argument("--padding", type=int, default=14)
    ap.add_argument("--base-ms", type=int, default=280)
    ap.add_argument("--ms-per-px", type=float, default=0.42)
    ap.add_argument("--final-hold-ms", type=int, default=700)
    ap.add_argument("--scene-id", default="scene-01")
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--no-stroke-previews", action="store_true", help="不輸出單筆檢查圖")
    args = ap.parse_args()

    summary = split_scene(
        text=args.text, font_path=args.font, size=args.size,
        width=args.width, height=args.height, bg=args.bg, ink=args.ink,
        padding=args.padding, base_ms=args.base_ms, ms_per_px=args.ms_per_px,
        final_hold_ms=args.final_hold_ms, scene_id=args.scene_id, out_dir=args.out_dir,
        write_stroke_previews=not args.no_stroke_previews)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
