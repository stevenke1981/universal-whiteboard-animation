#!/usr/bin/env python3
"""從字幕／文字來源建立可直接填入圖片與標注的白板動畫專案。"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from common import dump_json, dump_yaml, load_yaml
from parse_srt import group_scenes, parse_plain_text, parse_timed_text

SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROJECT = SKILL_ROOT / "config" / "default-project.yaml"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="建立通用白板動畫專案")
    parser.add_argument("--source", required=True, help="SRT、VTT 或文字稿")
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--project-name")
    parser.add_argument(
        "--subject-mode",
        choices=["none", "single", "ensemble", "object", "concept", "adaptive"],
        default="adaptive",
    )
    parser.add_argument("--subject-name")
    parser.add_argument("--subject-kind", default="human")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    source = Path(args.source).expanduser().resolve()
    project_dir = Path(args.project_dir).expanduser().resolve()
    if not source.exists():
        print(f"[err] 找不到來源: {source}", file=sys.stderr)
        return 2
    if project_dir.exists() and any(project_dir.iterdir()) and not args.overwrite:
        print(f"[err] 目錄非空；使用 --overwrite 或換目錄: {project_dir}", file=sys.stderr)
        return 2

    for directory in ("input", "scenes", "build/validation", "build/previews", "output"):
        (project_dir / directory).mkdir(parents=True, exist_ok=True)

    copied_source = project_dir / "input" / source.name
    if copied_source != source:
        shutil.copy2(source, copied_source)
    raw = copied_source.read_text(encoding="utf-8-sig")
    if "-->" in raw:
        cues, fmt, warnings = parse_timed_text(raw)
    else:
        cues, warnings = parse_plain_text(raw)
        fmt = "plain"
    if not cues:
        print("[err] 無法解析來源", file=sys.stderr)
        return 2

    template = load_yaml(DEFAULT_PROJECT)
    template["project"]["name"] = args.project_name or project_dir.name
    template["project"]["root"] = "."
    template["input"]["subtitles"] = f"input/{copied_source.name}"
    template["workflow"]["overwrite"] = args.overwrite
    template["subject_profile"]["mode"] = args.subject_mode
    if args.subject_name:
        subject_id = "subject-01"
        template["subject_profile"]["default_id"] = subject_id
        template["subject_profile"]["subjects"] = {
            subject_id: {
                "kind": args.subject_kind,
                "name": args.subject_name,
                "replaceable": True,
                "appearance": {},
                "identity_lock": [],
                "negative_constraints": [],
            }
        }

    segmentation = template["segmentation"]
    scenes, scene_warnings = group_scenes(
        cues,
        target_sec=float(segmentation["target_sec"]),
        min_sec=float(segmentation["min_sec"]),
        max_sec=float(segmentation["max_sec"]),
        prefer_punctuation=bool(segmentation["prefer_punctuation"]),
        gap_sec=float(segmentation["gap_sec"]),
    )
    warnings.extend(scene_warnings)
    template["scenes"] = [
        {
            "scene_id": scene["sceneId"],
            "start_ms": scene["startMs"],
            "end_ms": scene["endMs"],
            "duration_ms": scene["sceneDurationMs"],
            "cue_range": scene["cueRange"],
            "text": scene["text"],
            "core_message": "待代理依字幕提煉",
            "narrative_pattern": "adaptive",
            "subject_bindings": [],
            "image": None,
            "annotation": None,
            "output": f"output/{scene['sceneId']}.mp4",
        }
        for scene in scenes
    ]
    template["assumptions"] = warnings

    parsed = {
        "version": 1,
        "source": str(copied_source.relative_to(project_dir)),
        "format": fmt,
        "warnings": warnings,
        "cues": cues,
        "scenes": scenes,
    }
    dump_yaml(template, project_dir / "project.yaml")
    dump_json(parsed, project_dir / "build" / "parsed-scenes.json")
    print(f"PROJECT={project_dir}")
    print(f"SCENES={len(scenes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
