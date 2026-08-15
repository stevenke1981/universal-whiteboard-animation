from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from chinese_stroke_data import StrokeDataError, StrokeDataRepository, transform_hanzi_point
from chinese_stroke_split import find_default_font, plan_layout, split_scene
from chinese_whiteboard_renderer import ChineseRenderConfig, load_element_mask, render
from validate_annotation import validate


def _cross_data() -> dict:
    # 「十」：第一筆橫、第二筆豎。Make Me a Hanzi 座標的 y 軸向上。
    return {
        "character": "十",
        "strokes": [
            "M 180 535 L 844 535 L 844 485 L 180 485 Z",
            "M 485 820 L 539 820 L 539 160 L 485 160 Z",
        ],
        "medians": [
            [[210, 510], [810, 510]],
            [[512, 790], [512, 190]],
        ],
    }


def _write_data_dir(tmp_path: Path) -> Path:
    data_dir = tmp_path / "stroke-data"
    data_dir.mkdir()
    (data_dir / "十.json").write_text(
        json.dumps(_cross_data(), ensure_ascii=False),
        encoding="utf-8",
    )
    return data_dir


def _build_scene(tmp_path: Path) -> tuple[dict, Path, Path]:
    data_dir = _write_data_dir(tmp_path)
    summary = split_scene(
        text="十",
        font_path=None,
        size=180,
        width=480,
        height=320,
        bg="#F5EBD7",
        ink="#373737",
        padding=5,
        base_ms=100,
        ms_per_px=0.25,
        min_stroke_ms=100,
        max_stroke_ms=600,
        final_hold_ms=300,
        scene_id="cross",
        out_dir=tmp_path,
        stroke_data=data_dir,
        stroke_source="data",
    )
    return (
        summary,
        tmp_path / "scenes" / "cross.png",
        tmp_path / "scenes" / "cross.annotation.json",
    )


def test_repository_loads_directory_and_jsonl(tmp_path: Path) -> None:
    data_dir = _write_data_dir(tmp_path)
    item = StrokeDataRepository(data_dir).get("十")
    assert item is not None
    assert len(item.strokes) == 2
    assert item.medians[0][0] == (210.0, 510.0)

    jsonl = tmp_path / "graphics.txt"
    jsonl.write_text(json.dumps(_cross_data(), ensure_ascii=False) + "\n", encoding="utf-8")
    item_from_jsonl = StrokeDataRepository(jsonl).get("十")
    assert item_from_jsonl is not None
    assert item_from_jsonl.strokes == item.strokes


def test_coordinate_transform_preserves_median_direction() -> None:
    start = transform_hanzi_point((512, 790), (100, 50), 200)
    end = transform_hanzi_point((512, 190), (100, 50), 200)
    # 原資料由上往下寫豎筆；轉成一般畫布後 y 應由小到大。
    assert start[0] == pytest.approx(end[0])
    assert start[1] < end[1]


def test_plan_layout_is_left_to_right_without_font() -> None:
    origins = plan_layout("天地人", None, 100, 640, 360, char_gap=8)
    assert len(origins) == 3
    assert [point[0] for point in origins] == sorted(point[0] for point in origins)
    assert origins[1][0] - origins[0][0] == pytest.approx(108)


def test_split_scene_uses_authoritative_order_masks_and_medians(tmp_path: Path) -> None:
    summary, scene_path, annotation_path = _build_scene(tmp_path)
    assert summary["authoritative"] is True
    assert summary["strokes"] == 2
    assert scene_path.exists()

    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    assert data["writingSystem"]["strokeOrder"] == "data-array-order"
    assert data["writingSystem"]["strokeDirection"] == "median-start-to-end"
    first, second = data["elements"]
    assert [first["strokeIndex"], second["strokeIndex"]] == [1, 2]
    assert all(item["strokeOrderConfidence"] == "authoritative" for item in data["elements"])
    assert first["handPath"]["points"][0][0] < first["handPath"]["points"][-1][0]
    assert second["handPath"]["points"][0][1] < second["handPath"]["points"][-1][1]

    first_mask = annotation_path.parent / first["strokeMask"]
    second_mask = annotation_path.parent / second["strokeMask"]
    with Image.open(first_mask) as image:
        horizontal = np.asarray(image.convert("L")) > 0
    with Image.open(second_mask) as image:
        vertical = np.asarray(image.convert("L")) > 0
    hy, hx = np.where(horizontal)
    vy, vx = np.where(vertical)
    assert np.ptp(hx) > np.ptp(hy)
    assert np.ptp(vy) > np.ptp(vx)
    # 交叉像素可同時存在於兩個 mask，但渲染時每個 element 只拿自己的 mask。
    assert int((horizontal & vertical).sum()) > 0

    report = validate(scene_path, annotation_path)
    assert report["valid"] is True, report["issues"]
    assert report["summary"]["warnings"] == 0, report["issues"]


def test_renderer_uses_explicit_mask_and_authoritative_hand_path(tmp_path: Path) -> None:
    _, scene_path, annotation_path = _build_scene(tmp_path)
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    element = data["elements"][0]
    mask, resolved = load_element_mask(element, annotation_path, width=480, height=320)
    assert resolved is not None and resolved.exists()
    assert mask is not None and mask.any()

    output = tmp_path / "output" / "cross.mp4"
    report = render(
        scene_path,
        annotation_path,
        output,
        ChineseRenderConfig(
            fps=12,
            cap_long_edge=480,
            pointer="none",
            finalize_mode="union-only",
        ),
    )
    assert output.exists() and output.stat().st_size > 0
    assert all(item["writeMode"] is True for item in report["elements"])
    assert all(item["pathSource"] == "handPath.points" for item in report["elements"])
    assert all(item["explicitMask"] for item in report["elements"])

    capture = cv2.VideoCapture(str(output))
    assert capture.isOpened()
    frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    decoded: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        decoded.append(frame)
    capture.release()
    assert frames > 2 and len(decoded) == frames

    # 第一筆完成、第二筆尚未開始時，豎畫專屬區域必須仍是背景。
    first, second = data["elements"]
    first_mask, _ = load_element_mask(first, annotation_path, width=480, height=320)
    second_mask, _ = load_element_mask(second, annotation_path, width=480, height=320)
    assert first_mask is not None and second_mask is not None
    vertical_only = second_mask & ~first_mask
    vertical_only = cv2.erode(vertical_only.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    before_second_index = max(0, round(second["reveal"]["startMs"] * 12 / 1000) - 1)
    before_second = decoded[min(before_second_index, len(decoded) - 1)]
    background = np.array([0xD7, 0xEB, 0xF5], dtype=np.int16)  # #F5EBD7 in BGR
    changed_before = np.abs(before_second.astype(np.int16) - background).sum(axis=2) > 45
    assert int((changed_before & vertical_only).sum()) == 0

    # 最後一幀必須包含豎畫專屬區域。
    changed_final = np.abs(decoded[-1].astype(np.int16) - background).sum(axis=2) > 45
    assert int((changed_final & vertical_only).sum()) > 0


def test_strict_data_mode_rejects_missing_character(tmp_path: Path) -> None:
    data_dir = _write_data_dir(tmp_path)
    with pytest.raises(StrokeDataError, match="缺少 '口' 的權威筆畫資料"):
        split_scene(
            text="口",
            font_path=None,
            size=120,
            width=320,
            height=240,
            bg="#F5EBD7",
            ink="#373737",
            padding=4,
            base_ms=100,
            ms_per_px=0.2,
            out_dir=tmp_path,
            stroke_data=data_dir,
            stroke_source="data",
        )


def test_auto_font_fallback_is_explicitly_approximate(tmp_path: Path) -> None:
    font = find_default_font()
    if font is None:
        pytest.skip("系統沒有可用中文字型")
    summary = split_scene(
        text="！",
        font_path=str(font),
        size=120,
        width=320,
        height=240,
        bg="#F5EBD7",
        ink="#373737",
        padding=4,
        base_ms=100,
        ms_per_px=0.2,
        out_dir=tmp_path,
        stroke_source="auto",
        scene_id="punctuation",
    )
    assert summary["warnings"]
    data = json.loads((tmp_path / "scenes" / "punctuation.annotation.json").read_text(encoding="utf-8"))
    assert data["elements"][0]["strokeOrderConfidence"] == "approximate"
    assert data["elements"][0]["strokeSource"] == "font-glyph-fallback"
