from __future__ import annotations

from pathlib import Path

import cv2
from PIL import Image, ImageDraw

from common import dump_json
from render_whiteboard import RenderConfig, render


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    image_path = tmp_path / "source.png"
    image = Image.new("RGB", (320, 180), "#F5EBD7")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((35, 40, 130, 145), radius=16, outline="#333333", width=5, fill="#D96B3B")
    draw.ellipse((185, 45, 285, 145), outline="#333333", width=5, fill="#3B82B8")
    image.save(image_path)

    annotation_path = tmp_path / "source.annotation.json"
    dump_json(
        {
            "version": 1,
            "sceneId": "scene-smoke",
            "canvas": {"width": 320, "height": 180},
            "background": "#F5EBD7",
            "sceneDurationMs": 1400,
            "finalHoldMs": 250,
            "elements": [
                {
                    "id": "left",
                    "label": "左側物件",
                    "sequence": 1,
                    "narrativeRole": "起點",
                    "subtitle": "先畫左側物件。",
                    "maskPolicy": "explicit",
                    "region": {"x": 20, "y": 20, "width": 130, "height": 145},
                    "reveal": {"startMs": 0, "durationMs": 450, "direction": "top_to_bottom", "protectedRegions": []},
                },
                {
                    "id": "right",
                    "label": "右側物件",
                    "sequence": 2,
                    "narrativeRole": "結果",
                    "subtitle": "再畫右側物件。",
                    "maskPolicy": "explicit",
                    "region": {"x": 165, "y": 20, "width": 140, "height": 145},
                    "reveal": {"startMs": 500, "durationMs": 450, "direction": "radial", "protectedRegions": []},
                },
            ],
        },
        annotation_path,
    )
    return image_path, annotation_path


def _assert_video(path: Path) -> None:
    capture = cv2.VideoCapture(str(path))
    assert capture.isOpened()
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    ok_first, first = capture.read()
    assert ok_first
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count - 1))
    ok_last, last = capture.read()
    capture.release()
    assert ok_last
    assert frame_count >= 8
    # 首幀接近乾淨米黃底，末幀必須出現更大的像素差異。
    assert float(first.std()) < float(last.std())


def test_grid_renderer_smoke(tmp_path: Path) -> None:
    image, annotation = _fixture(tmp_path)
    output = tmp_path / "grid.mp4"
    report = render(
        image,
        annotation,
        output,
        RenderConfig(fps=8, cap_long_edge=320, grid_edge=8, ink_path="grid", pointer="none"),
    )
    assert report["valid"]
    assert output.exists() and output.stat().st_size > 0
    _assert_video(output)


def test_skeleton_renderer_smoke(tmp_path: Path) -> None:
    image, annotation = _fixture(tmp_path)
    output = tmp_path / "skeleton.mp4"
    report = render(
        image,
        annotation,
        output,
        RenderConfig(fps=8, cap_long_edge=320, grid_edge=8, ink_path="skeleton", pointer="none"),
    )
    assert report["valid"]
    assert output.exists() and output.stat().st_size > 0
    _assert_video(output)
