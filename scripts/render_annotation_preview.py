#!/usr/bin/env python3
"""產生跨平台的 annotation 區域、順序、方向與時間檢查圖。"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import load_json

FONT_CANDIDATES = [
    # Windows
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/NotoSansTC-Regular.otf",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    # Linux / common containers
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
PALETTE = [
    (40, 105, 235, 230),
    (225, 80, 70, 230),
    (45, 160, 100, 230),
    (160, 95, 220, 230),
    (225, 145, 40, 230),
    (35, 155, 175, 230),
]


def find_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    custom = os.environ.get("WHITEBOARD_FONT")
    candidates = [custom] if custom else []
    candidates.extend(FONT_CANDIDATES)
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _text_box(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, *, padding: int = 6):
    x, y = xy
    left, top, right, bottom = draw.textbbox((x, y), text, font=font)
    return (left - padding, top - padding, right + padding, bottom + padding)


def _arrow_points(element: dict) -> tuple[tuple[int, int], tuple[int, int]]:
    hand_path = element.get("handPath") or {}
    if isinstance(hand_path.get("start"), list) and isinstance(hand_path.get("end"), list):
        return tuple(map(int, hand_path["start"][:2])), tuple(map(int, hand_path["end"][:2]))
    r = element["region"]
    x, y, w, h = r["x"], r["y"], r["width"], r["height"]
    direction = (element.get("reveal") or {}).get("direction", "auto")
    if direction == "right_to_left":
        return (x + w - 12, y + h // 2), (x + 12, y + h // 2)
    if direction == "top_to_bottom":
        return (x + w // 2, y + 12), (x + w // 2, y + h - 12)
    if direction == "bottom_to_top":
        return (x + w // 2, y + h - 12), (x + w // 2, y + 12)
    return (x + 12, y + h // 2), (x + w - 12, y + h // 2)


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color) -> None:
    draw.line((start, end), fill=color, width=4)
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    back_x, back_y = end[0] - ux * 16, end[1] - uy * 16
    p1 = (end[0], end[1])
    p2 = (int(back_x + px * 7), int(back_y + py * 7))
    p3 = (int(back_x - px * 7), int(back_y - py * 7))
    draw.polygon((p1, p2, p3), fill=color)


def render_preview(image_path: Path, annotation_path: Path, output_path: Path) -> None:
    image = Image.open(image_path).convert("RGBA")
    data = load_json(annotation_path)
    canvas = data.get("canvas") or {}
    if (canvas.get("width"), canvas.get("height")) != image.size:
        raise ValueError(
            f"圖片尺寸 {image.size[0]}x{image.size[1]} 與 canvas "
            f"{canvas.get('width')}x{canvas.get('height')} 不一致"
        )

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    label_font = find_font(max(16, round(image.width / 70)))
    small_font = find_font(max(13, round(image.width / 95)))

    elements = sorted(data.get("elements", []), key=lambda item: item.get("sequence", 10**9))
    for index, element in enumerate(elements, start=1):
        region = element["region"]
        x, y = region["x"], region["y"]
        right = x + region["width"]
        bottom = y + region["height"]
        color = PALETTE[(index - 1) % len(PALETTE)]
        fill = (*color[:3], 28)
        draw.rounded_rectangle((x, y, right, bottom), radius=10, outline=color, width=4, fill=fill)

        badge_size = max(28, round(image.width / 40))
        draw.ellipse((x + 8, y + 8, x + 8 + badge_size, y + 8 + badge_size), fill=color)
        draw.text(
            (x + 8 + badge_size / 2, y + 8 + badge_size / 2),
            str(element.get("sequence", index)),
            anchor="mm",
            font=small_font,
            fill="white",
        )

        reveal = element.get("reveal") or {}
        start = int(reveal.get("startMs", 0))
        end = start + int(reveal.get("durationMs", 0))
        subject_ids = ",".join(element.get("subjectIds") or [])
        suffix = f"  [{subject_ids}]" if subject_ids else ""
        label = (
            f"{element.get('sequence', index)}. {element.get('label', element.get('id', 'element'))}{suffix}  "
            f"{start/1000:.1f}-{end/1000:.1f}s  {reveal.get('direction', 'auto')}"
        )
        tx = x + badge_size + 18
        ty = y + 12
        box = _text_box(draw, (tx, ty), label, label_font, padding=7)
        # 限制標籤背景不要超出畫布。
        shift_x = min(0, image.width - box[2] - 4)
        if shift_x:
            tx += shift_x
            box = _text_box(draw, (tx, ty), label, label_font, padding=7)
        draw.rounded_rectangle(box, radius=6, fill=(255, 255, 255, 232), outline=color, width=2)
        draw.text((tx, ty), label, font=label_font, fill=color)

        arrow_start, arrow_end = _arrow_points(element)
        _draw_arrow(draw, arrow_start, arrow_end, color)

        for protected in reveal.get("protectedRegions", []) or []:
            px, py = protected["x"], protected["y"]
            pr, pb = px + protected["width"], py + protected["height"]
            draw.rectangle((px, py, pr, pb), outline=(215, 30, 30, 230), width=3)
            draw.line((px, py, pr, pb), fill=(215, 30, 30, 180), width=2)
            draw.line((pr, py, px, pb), fill=(215, 30, 30, 180), width=2)

    result = Image.alpha_composite(image, overlay).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, quality=95)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="產生白板 annotation 區域檢查圖")
    parser.add_argument("image")
    parser.add_argument("annotation")
    parser.add_argument("output")
    args = parser.parse_args(argv)
    try:
        output = Path(args.output)
        render_preview(Path(args.image), Path(args.annotation), output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    print(f"OUTPUT={output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
