#!/usr/bin/env python3
"""產生不含猴子的兩幕通用白板動畫 demo 圖、標注、字幕與 project.yaml。"""
from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

from common import dump_json, dump_yaml

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEMO_ROOT = SKILL_ROOT / "examples" / "demo"
BG = "#F5EBD7"
INK = "#373737"
BLUE = "#3B82B8"
ORANGE = "#D96B3B"
YELLOW = "#E5AA3D"


def draw_person(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, accent: str, pose: str = "open") -> None:
    head_r = int(36 * scale)
    draw.ellipse((cx - head_r, cy - 170 * scale - head_r, cx + head_r, cy - 170 * scale + head_r), outline=INK, width=max(2, int(5 * scale)), fill=BG)
    draw.arc((cx - head_r // 2, cy - 170 * scale - head_r // 2, cx + head_r // 2, cy - 170 * scale + head_r // 2), 200, 340, fill=INK, width=max(1, int(3 * scale)))
    body_top = int(cy - 125 * scale)
    body_bottom = int(cy + 35 * scale)
    draw.rounded_rectangle((cx - 48 * scale, body_top, cx + 48 * scale, body_bottom), radius=int(18 * scale), outline=INK, width=max(2, int(5 * scale)), fill=accent)
    if pose == "point":
        draw.line((cx - 40 * scale, body_top + 30 * scale, cx - 120 * scale, body_top - 15 * scale), fill=INK, width=max(2, int(6 * scale)))
        draw.line((cx + 40 * scale, body_top + 30 * scale, cx + 95 * scale, body_top + 70 * scale), fill=INK, width=max(2, int(6 * scale)))
    else:
        draw.line((cx - 40 * scale, body_top + 28 * scale, cx - 105 * scale, body_top + 75 * scale), fill=INK, width=max(2, int(6 * scale)))
        draw.line((cx + 40 * scale, body_top + 28 * scale, cx + 105 * scale, body_top + 75 * scale), fill=INK, width=max(2, int(6 * scale)))
    draw.line((cx - 22 * scale, body_bottom, cx - 55 * scale, cy + 150 * scale), fill=INK, width=max(2, int(7 * scale)))
    draw.line((cx + 22 * scale, body_bottom, cx + 55 * scale, cy + 150 * scale), fill=INK, width=max(2, int(7 * scale)))


def draw_bulb(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float = 1.0) -> None:
    r = int(78 * scale)
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=max(3, int(6 * scale)), fill="#F4D66B")
    draw.line((cx - 35 * scale, cy + 62 * scale, cx - 25 * scale, cy + 115 * scale), fill=INK, width=max(2, int(6 * scale)))
    draw.line((cx + 35 * scale, cy + 62 * scale, cx + 25 * scale, cy + 115 * scale), fill=INK, width=max(2, int(6 * scale)))
    draw.rounded_rectangle((cx - 30 * scale, cy + 105 * scale, cx + 30 * scale, cy + 142 * scale), radius=int(8 * scale), outline=INK, width=max(2, int(5 * scale)), fill=BLUE)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        start = (cx + math.cos(rad) * r * 1.3, cy + math.sin(rad) * r * 1.3)
        end = (cx + math.cos(rad) * r * 1.65, cy + math.sin(rad) * r * 1.65)
        draw.line((start, end), fill=YELLOW, width=max(2, int(6 * scale)))


def draw_prototype(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int) -> None:
    draw.rounded_rectangle((x, y, x + w, y + h), radius=28, outline=INK, width=6, fill="#E9E2D2")
    draw.rounded_rectangle((x + 35, y + 38, x + w - 35, y + h - 95), radius=20, outline=INK, width=5, fill="#D7E8F2")
    draw.ellipse((x + w // 2 - 17, y + h - 64, x + w // 2 + 17, y + h - 30), outline=INK, width=5, fill=ORANGE)
    draw.line((x + 70, y + 90, x + w - 70, y + 90), fill=BLUE, width=8)
    draw.line((x + 70, y + 145, x + w - 130, y + 145), fill=INK, width=5)
    draw.line((x + 70, y + 195, x + w - 95, y + 195), fill=INK, width=5)


def draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str = INK) -> None:
    draw.line((start, end), fill=color, width=6)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    for offset in (2.55, -2.55):
        p = (end[0] + math.cos(angle + offset) * 22, end[1] + math.sin(angle + offset) * 22)
        draw.line((end, p), fill=color, width=6)


def scene_one(path: Path) -> None:
    image = Image.new("RGB", (1280, 720), BG)
    draw = ImageDraw.Draw(image)
    draw_person(draw, 205, 440, 1.0, ORANGE, pose="point")
    draw_bulb(draw, 585, 275, 1.0)
    draw_prototype(draw, 835, 135, 330, 445)
    draw_arrow(draw, (340, 315), (460, 285), BLUE)
    draw_arrow(draw, (700, 315), (810, 315), BLUE)
    image.save(path)


def scene_two(path: Path) -> None:
    image = Image.new("RGB", (1280, 720), BG)
    draw = ImageDraw.Draw(image)
    draw_person(draw, 190, 440, 1.0, BLUE, pose="open")
    draw_prototype(draw, 465, 145, 320, 430)
    draw_person(draw, 1015, 440, 0.92, ORANGE, pose="point")
    # 回饋循環與完成符號，不使用文字。
    draw.arc((345, 70, 910, 660), 205, 335, fill=YELLOW, width=8)
    draw.arc((345, 70, 910, 660), 25, 155, fill=YELLOW, width=8)
    draw.polygon(((382, 178), (355, 132), (410, 140)), fill=YELLOW)
    draw.polygon(((874, 552), (901, 598), (846, 590)), fill=YELLOW)
    draw.line((1060, 120, 1105, 165), fill="#3B9B65", width=13)
    draw.line((1105, 165, 1190, 70), fill="#3B9B65", width=13)
    image.save(path)


def make_annotation(scene_id: str, basis: str, elements: list[dict]) -> dict:
    return {
        "version": 1,
        "sceneId": scene_id,
        "canvas": {"width": 1280, "height": 720},
        "background": BG,
        "storyBasis": basis,
        "coreMessage": basis,
        "sceneDurationMs": 6000,
        "finalHoldMs": 700,
        "elements": elements,
    }


def main() -> int:
    scenes_dir = DEMO_ROOT / "scenes"
    output_dir = DEMO_ROOT / "output"
    build_dir = DEMO_ROOT / "build"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    srt = """1
00:00:00,000 --> 00:00:02,600
設計師先把問題整理成一個清楚的想法。

2
00:00:02,600 --> 00:00:05,700
團隊再把想法組成可以測試的原型。

3
00:00:06,000 --> 00:00:08,700
使用者實際操作，找出最重要的問題。

4
00:00:08,700 --> 00:00:11,600
最後依回饋調整流程，讓成果真正能被使用。
"""
    (DEMO_ROOT / "story.srt").write_text(srt, encoding="utf-8")

    image1 = scenes_dir / "scene-01-idea-to-prototype.png"
    image2 = scenes_dir / "scene-02-feedback-loop.png"
    scene_one(image1)
    scene_two(image2)

    ann1 = make_annotation(
        "scene-01",
        "設計師把問題化成想法，團隊再做成可測試原型。",
        [
            {
                "id": "designer",
                "label": "提出想法的設計師",
                "sequence": 1,
                "type": "character",
                "narrativeRole": "問題與想法的起點",
                "subtitle": "設計師先把問題整理成一個清楚的想法。",
                "subjectIds": ["creator"],
                "maskPolicy": "explicit",
                "region": {"x": 35, "y": 115, "width": 355, "height": 535},
                "reveal": {"direction": "top_to_bottom", "startMs": 0, "durationMs": 1450, "protectedRegions": []},
            },
            {
                "id": "idea",
                "label": "被整理出的想法",
                "sequence": 2,
                "type": "concept",
                "narrativeRole": "核心概念具象化",
                "subtitle": "設計師先把問題整理成一個清楚的想法。",
                "subjectIds": ["idea"],
                "maskPolicy": "explicit",
                "region": {"x": 405, "y": 90, "width": 355, "height": 390},
                "reveal": {"direction": "radial", "startMs": 1600, "durationMs": 1350, "protectedRegions": []},
            },
            {
                "id": "prototype",
                "label": "可測試的原型",
                "sequence": 3,
                "type": "product",
                "narrativeRole": "想法轉成可操作成果",
                "subtitle": "團隊再把想法組成可以測試的原型。",
                "subjectIds": ["prototype"],
                "maskPolicy": "explicit",
                "region": {"x": 780, "y": 90, "width": 440, "height": 545},
                "reveal": {"direction": "left_to_right", "startMs": 3150, "durationMs": 1750, "protectedRegions": []},
            },
        ],
    )
    ann2 = make_annotation(
        "scene-02",
        "使用者測試原型，團隊依回饋迭代並完成可用成果。",
        [
            {
                "id": "user",
                "label": "實際操作的使用者",
                "sequence": 1,
                "type": "character",
                "narrativeRole": "測試與回饋來源",
                "subtitle": "使用者實際操作，找出最重要的問題。",
                "subjectIds": ["user"],
                "maskPolicy": "explicit",
                "region": {"x": 25, "y": 110, "width": 340, "height": 545},
                "reveal": {"direction": "top_to_bottom", "startMs": 0, "durationMs": 1400, "protectedRegions": []},
            },
            {
                "id": "tested-prototype",
                "label": "接受測試的原型",
                "sequence": 2,
                "type": "product",
                "narrativeRole": "被檢驗的方案",
                "subtitle": "使用者實際操作，找出最重要的問題。",
                "subjectIds": ["prototype"],
                "maskPolicy": "explicit",
                "region": {"x": 400, "y": 80, "width": 445, "height": 570},
                "reveal": {"direction": "left_to_right", "startMs": 1550, "durationMs": 1550, "protectedRegions": []},
            },
            {
                "id": "iteration-result",
                "label": "迭代後的完成結果",
                "sequence": 3,
                "type": "result",
                "narrativeRole": "回饋、調整與完成",
                "subtitle": "最後依回饋調整流程，讓成果真正能被使用。",
                "subjectIds": ["creator", "result"],
                "maskPolicy": "explicit",
                "region": {"x": 825, "y": 50, "width": 410, "height": 610},
                "reveal": {"direction": "bottom_to_top", "startMs": 3300, "durationMs": 1700, "protectedRegions": []},
            },
        ],
    )
    dump_json(ann1, scenes_dir / "scene-01-idea-to-prototype.annotation.json")
    dump_json(ann2, scenes_dir / "scene-02-feedback-loop.annotation.json")

    project = {
        "version": 1,
        "project": {"name": "replaceable-subject-demo", "language": "zh-TW", "root": "."},
        "workflow": {"mode": "auto", "overwrite": True},
        "input": {"subtitles": "story.srt", "audio": None, "script": None},
        "paths": {"scenes": "scenes", "build": "build", "output": "output"},
        "segmentation": {"target_sec": 6, "min_sec": 3, "max_sec": 8, "prefer_punctuation": True, "gap_sec": 0.25},
        "canvas": {"width": 1280, "height": 720, "fps": 12, "background": BG},
        "subject_profile": {
            "mode": "ensemble",
            "default_id": "creator",
            "subjects": {
                "creator": {"kind": "human", "name": "設計師", "replaceable": True, "appearance": {"outfit": "orange"}, "identity_lock": ["silhouette", "outfit"], "negative_constraints": ["不可自動替換成猴子"]},
                "user": {"kind": "human", "name": "使用者", "replaceable": True, "appearance": {"outfit": "blue"}, "identity_lock": ["silhouette", "outfit"], "negative_constraints": []},
                "idea": {"kind": "concept", "name": "想法", "replaceable": True, "appearance": {"symbol": "lightbulb"}, "identity_lock": [], "negative_constraints": []},
                "prototype": {"kind": "product", "name": "原型", "replaceable": True, "appearance": {"shape": "rounded-device"}, "identity_lock": ["silhouette"], "negative_constraints": []},
                "result": {"kind": "concept", "name": "完成結果", "replaceable": True, "appearance": {"symbol": "check"}, "identity_lock": [], "negative_constraints": []}
            },
        },
        "visual": {"preset": "minimal-paper", "line_color": INK, "accent_colors": [ORANGE, BLUE, YELLOW], "source_text_policy": "subtitles-only"},
        "render": {"ink_path": "skeleton", "color_fill": "wipe", "pointer": "pen", "cap_long_edge": 640, "grid_edge": 8, "ink_color_ratio": [2, 1], "final_hold_ms": 700, "mask_policy": None, "finalize_mode": "union-only", "h264": True},
        "finalize": {"merge": True, "output": "output/final.mp4", "audio": None, "subtitles": None, "subtitle_mode": "none"},
        "scenes": [
            {"scene_id": "scene-01", "start_ms": 0, "end_ms": 5700, "duration_ms": 5700, "cue_range": [1, 2], "text": "設計師先把問題整理成一個清楚的想法。團隊再把想法組成可以測試的原型。", "core_message": "從想法到原型", "narrative_pattern": "problem-solution", "subject_bindings": ["creator", "idea", "prototype"], "image": "scenes/scene-01-idea-to-prototype.png", "annotation": "scenes/scene-01-idea-to-prototype.annotation.json", "output": "output/scene-01.mp4"},
            {"scene_id": "scene-02", "start_ms": 6000, "end_ms": 11600, "duration_ms": 5600, "cue_range": [3, 4], "text": "使用者實際操作，找出最重要的問題。最後依回饋調整流程，讓成果真正能被使用。", "core_message": "測試、回饋與迭代", "narrative_pattern": "test-feedback-result", "subject_bindings": ["user", "prototype", "creator", "result"], "image": "scenes/scene-02-feedback-loop.png", "annotation": "scenes/scene-02-feedback-loop.annotation.json", "output": "output/scene-02.mp4"}
        ],
        "assumptions": ["Demo 主體全部可替換，沒有固定猴子角色。"],
    }
    dump_yaml(project, DEMO_ROOT / "project.yaml")
    print(f"DEMO={DEMO_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
