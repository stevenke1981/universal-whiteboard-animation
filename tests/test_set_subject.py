from __future__ import annotations

from pathlib import Path

from common import dump_json, dump_yaml, load_json, load_yaml
from set_subject import update_subject


def test_replace_subject_updates_project_and_annotation(tmp_path: Path) -> None:
    annotation = tmp_path / "scene.annotation.json"
    dump_json(
        {
            "sceneId": "scene-01",
            "canvas": {"width": 10, "height": 10},
            "sceneDurationMs": 1000,
            "elements": [
                {
                    "id": "character",
                    "label": "角色",
                    "sequence": 1,
                    "subjectIds": ["creator", "idea"],
                    "region": {"x": 0, "y": 0, "width": 10, "height": 10},
                    "reveal": {"startMs": 0, "durationMs": 500},
                }
            ],
        },
        annotation,
    )
    project_file = tmp_path / "project.yaml"
    dump_yaml(
        {
            "subject_profile": {
                "mode": "ensemble",
                "default_id": "creator",
                "subjects": {
                    "creator": {"kind": "human", "name": "舊角色", "replaceable": True, "appearance": {}},
                    "idea": {"kind": "concept", "name": "想法", "replaceable": True, "appearance": {}},
                },
            },
            "scenes": [{"scene_id": "scene-01", "subject_bindings": ["creator", "idea"], "annotation": "scene.annotation.json"}],
        },
        project_file,
    )

    report = update_subject(
        project_file,
        subject_id="host",
        replace_id="creator",
        mode="single",
        name="新主持人",
        kind="human",
        appearance={"outfit": "blue-jacket"},
        identity_lock=["face", "outfit"],
        negative_constraints=["不可變成動物"],
        replaceable=True,
        set_default=True,
        remove=False,
        update_annotations=True,
        dry_run=False,
        backup=False,
    )
    assert report["changed"]
    project = load_yaml(project_file)
    assert "creator" not in project["subject_profile"]["subjects"]
    assert project["subject_profile"]["default_id"] == "host"
    assert project["scenes"][0]["subject_bindings"] == ["host", "idea"]
    assert load_json(annotation)["elements"][0]["subjectIds"] == ["host", "idea"]
