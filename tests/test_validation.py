from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from common import dump_json
from validate_annotation import validate


def _valid_annotation() -> dict:
    return {
        "version": 1,
        "sceneId": "scene-01",
        "canvas": {"width": 320, "height": 180},
        "background": "#F5EBD7",
        "sceneDurationMs": 2500,
        "finalHoldMs": 500,
        "elements": [
            {
                "id": "object-a",
                "label": "物件 A",
                "sequence": 1,
                "narrativeRole": "建立情境",
                "subtitle": "先建立情境。",
                "subjectIds": ["subject-a"],
                "maskPolicy": "explicit",
                "region": {"x": 20, "y": 20, "width": 120, "height": 130},
                "reveal": {
                    "direction": "top_to_bottom",
                    "startMs": 0,
                    "durationMs": 900,
                    "protectedRegions": [],
                },
            },
            {
                "id": "object-b",
                "label": "物件 B",
                "sequence": 2,
                "narrativeRole": "呈現結果",
                "subtitle": "再呈現結果。",
                "subjectIds": ["subject-b"],
                "maskPolicy": "explicit",
                "region": {"x": 170, "y": 20, "width": 120, "height": 130},
                "reveal": {
                    "direction": "left_to_right",
                    "startMs": 1000,
                    "durationMs": 900,
                    "protectedRegions": [],
                },
            },
        ],
    }


def test_valid_annotation(tmp_path: Path) -> None:
    image_path = tmp_path / "scene.png"
    Image.new("RGB", (320, 180), "#F5EBD7").save(image_path)
    annotation_path = tmp_path / "scene.annotation.json"
    dump_json(_valid_annotation(), annotation_path)

    report = validate(image_path, annotation_path)
    assert report["valid"]
    assert report["summary"]["errors"] == 0


def test_validator_rejects_bounds_and_sequence(tmp_path: Path) -> None:
    image_path = tmp_path / "scene.png"
    Image.new("RGB", (320, 180), "#F5EBD7").save(image_path)
    data = _valid_annotation()
    data["elements"][1]["sequence"] = 4
    data["elements"][1]["region"]["x"] = 300
    annotation_path = tmp_path / "bad.annotation.json"
    annotation_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    report = validate(image_path, annotation_path)
    assert not report["valid"]
    codes = {item["code"] for item in report["issues"]}
    assert "sequence-gap" in codes
    assert "region-out-of-bounds" in codes
