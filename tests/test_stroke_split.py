from __future__ import annotations

import json
from pathlib import Path

import pytest

from chinese_stroke_split import (
    decompose_contours,
    plan_layout,
    split_scene,
    stroke_key,
)

KAIU = Path(r"C:\Windows\Fonts\kaiu.ttf")
needs_kaiu = pytest.mark.skipif(not KAIU.exists(), reason="需要 Windows 標楷體 kaiu.ttf")


@needs_kaiu
def test_plan_layout_positions_are_ordered_and_centered() -> None:
    origins = plan_layout("日日是好日！", str(KAIU), 100, 640, 360)
    assert len(origins) == 6
    xs = [o[0] for o in origins]
    # 逐字由左至右、間距一致
    assert xs == sorted(xs)
    assert len(set(round(x, 1) for x in xs)) == 6
    # 垂直位於畫布內（字面 top offset 已內建，不做精確斷言）
    assert all(0 < o[1] < 360 for o in origins)


@needs_kaiu
def test_decompose_ri_gives_six_contours() -> None:
    contours = decompose_contours(str(KAIU), "日", 1000, 100 / 1000, (50.0, 100.0))
    # 標楷體「日」= 6 條輪廓（外框、內框、兩短橫 ×2 結構）
    assert len(contours) == 6
    for pts in contours:
        assert len(pts) >= 3
        assert all(isinstance(x, float) and isinstance(y, float) for x, y in pts)


def test_clamp_region_stays_inside_canvas() -> None:
    from chinese_stroke_split import clamp_region

    region = clamp_region(-10, -4, 650, 370, 640, 360, padding=14)
    assert region["x"] >= 0 and region["y"] >= 0
    assert region["x"] + region["width"] <= 640
    assert region["y"] + region["height"] <= 360
    assert region["width"] >= 1 and region["height"] >= 1


@needs_kaiu
def test_stroke_key_orders_horizontal_before_vertical() -> None:
    # 相同 y 層：寬大於高的「一」先於窄高的「丨」
    flat = (0.0, 0.0, 80.0, 10.0)   # 橫：w=80 h=10
    tall = (100.0, 0.0, 110.0, 80.0)  # 豎：w=10 h=80
    assert stroke_key(flat, 100.0) < stroke_key(tall, 100.0)


@needs_kaiu
def test_split_scene_ri_smoke(tmp_path: Path) -> None:
    scene = split_scene(
        text="日",
        font_path=str(KAIU),
        size=100,
        width=640,
        height=360,
        bg="#F5EBD7",
        ink="#373737",
        padding=6,
        scene_id="test-ri",
        out_dir=str(tmp_path),
        base_ms=280,
        ms_per_px=0.42,
    )
    assert scene["chars"] == 1
    assert scene["strokes"] == 6
    assert scene["perChar"]["日"] == 6
    assert scene["sceneDurationMs"] > 0

    image = tmp_path / "scenes" / "test-ri.png"
    annotation = tmp_path / "scenes" / "test-ri.annotation.json"
    assert image.exists() and image.stat().st_size > 0
    assert annotation.exists()

    data = json.loads(annotation.read_text(encoding="utf-8"))
    assert data["sceneDurationMs"] == scene["sceneDurationMs"]
    elements = data["elements"]
    assert len(elements) == 6
    for i, e in enumerate(elements):
        assert e["sequence"] == i + 1
        assert e["type"] == "text-stroke"
        r = e["region"]
        assert all(isinstance(v, int) for v in (r["x"], r["y"], r["width"], r["height"]))
        assert r["x"] >= 0 and r["y"] >= 0
        assert r["x"] + r["width"] <= 640
        assert r["y"] + r["height"] <= 360
        assert e["reveal"]["direction"] in ("left_to_right", "top_to_bottom")
        assert 220 <= e["reveal"]["durationMs"] <= 950
        path = e["handPath"]
        assert path["kind"] == "stroke-centerline"
        assert len(path["contour"]) >= 3
        assert len(path["points"]) >= 2
        assert path["start"] == path["points"][0]
        assert path["end"] == path["points"][-1]
        px, py = path["points"][0]
        assert r["x"] - 8 <= px <= r["x"] + r["width"] + 8
        assert r["y"] - 8 <= py <= r["y"] + r["height"] + 8


@needs_kaiu
def test_split_scene_full_sentence_smoke(tmp_path: Path) -> None:
    scene = split_scene(
        text="日日是好日！",
        font_path=str(KAIU),
        size=120,
        width=960,
        height=540,
        bg="#F5EBD7",
        ink="#373737",
        padding=6,
        scene_id="test-sentence",
        out_dir=str(tmp_path),
        base_ms=280,
        ms_per_px=0.42,
    )
    assert scene["chars"] == 6
    assert scene["strokes"] == 42
    assert scene["perChar"] == {"日": 6, "是": 11, "好": 11, "！": 2}
    assert scene["sceneDurationMs"] > 0

    data = json.loads((tmp_path / "scenes" / "test-sentence.annotation.json").read_text(encoding="utf-8"))
    assert len(data["elements"]) == 42
    # 最後一筆畫在場景時長內結束
    last = data["elements"][-1]
    assert last["reveal"]["startMs"] + last["reveal"]["durationMs"] <= data["sceneDurationMs"]