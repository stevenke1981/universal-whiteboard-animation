#!/usr/bin/env python3
"""執行 demo 的端到端驗收，輸出可機讀 JSON 報告。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from batch_render import batch_render
from common import dump_json, ffprobe_path, load_json, load_yaml, resolve_project_path
from generate_demo_assets import main as generate_demo
from parse_srt import group_scenes, parse_timed_text
from validate_annotation import validate
from validate_project import validate_project


def inspect_video(path: Path, expected_background: str | None = None) -> dict:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return {"valid": False, "path": str(path), "error": "open-failed"}
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    ok_first, first = capture.read()
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(0, frame_count - 1))
    ok_last, last = capture.read()
    capture.release()
    if not ok_first or not ok_last:
        return {"valid": False, "path": str(path), "error": "frame-read-failed"}

    clean_score = None
    if expected_background:
        digits = expected_background.lstrip("#")
        rgb = np.array([int(digits[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)
        bgr = rgb[::-1]
        clean_score = float(np.abs(first.astype(np.float32) - bgr).mean())
    final_change = float(np.abs(last.astype(np.float32) - first.astype(np.float32)).mean())
    return {
        "valid": frame_count > 1 and fps > 0 and width > 0 and height > 0,
        "path": str(path),
        "sizeBytes": path.stat().st_size if path.exists() else 0,
        "width": width,
        "height": height,
        "fps": fps,
        "frameCount": frame_count,
        "durationSec": frame_count / fps if fps else 0,
        "firstFrameBackgroundMae": clean_score,
        "firstFrameClean": clean_score is None or clean_score < 18.0,
        "lastFrameMeanChange": final_change,
        "lastFrameHasDrawing": final_change > 2.0,
    }


def run(project_file: Path, *, full_res: bool = False) -> dict:
    project_file = project_file.resolve()
    if not project_file.exists() and project_file.name == "project.yaml":
        generate_demo()
    project = load_yaml(project_file)
    root = project_file.parent
    checks: list[dict] = []

    project_report = validate_project(project_file)
    checks.append({"name": "project-schema-and-paths", "passed": project_report["valid"], "detail": project_report})

    subtitle_path = resolve_project_path(project_file, (project.get("input") or {}).get("subtitles"))
    if subtitle_path and subtitle_path.exists():
        cues, fmt, parse_warnings = parse_timed_text(subtitle_path.read_text(encoding="utf-8-sig"))
        segmentation = project.get("segmentation") or {}
        scenes, scene_warnings = group_scenes(
            cues,
            target_sec=float(segmentation.get("target_sec", 22)),
            min_sec=float(segmentation.get("min_sec", 8)),
            max_sec=float(segmentation.get("max_sec", 35)),
            prefer_punctuation=bool(segmentation.get("prefer_punctuation", True)),
            gap_sec=float(segmentation.get("gap_sec", 1.2)),
        )
        expected = len(project.get("scenes") or [])
        checks.append(
            {
                "name": "subtitle-segmentation",
                "passed": len(cues) > 0 and len(scenes) == expected,
                "detail": {"format": fmt, "cueCount": len(cues), "sceneCount": len(scenes), "expected": expected, "warnings": parse_warnings + scene_warnings},
            }
        )

    for scene in project.get("scenes") or []:
        image = resolve_project_path(project_file, scene.get("image"))
        annotation = resolve_project_path(project_file, scene.get("annotation"))
        if image is None or annotation is None:
            checks.append({"name": f"{scene.get('scene_id')}-annotation", "passed": False, "detail": "missing image/annotation"})
            continue
        report = validate(image, annotation)
        checks.append({"name": f"{scene.get('scene_id')}-annotation", "passed": report["valid"], "detail": report})

    batch = batch_render(
        project_file,
        low_res=not full_res,
        no_finalize=False,
        continue_on_error=False,
        only=None,
    )
    checks.append({"name": "batch-render", "passed": batch["valid"], "detail": batch})

    background = str((project.get("canvas") or {}).get("background", "#F5EBD7"))
    video_reports: list[dict] = []
    for output in batch.get("outputs") or []:
        video_reports.append(inspect_video(Path(output), background))
    final_output = None
    if batch.get("final"):
        final_output = Path(batch["final"]["output"])
        video_reports.append(inspect_video(final_output, background))
    for video in video_reports:
        checks.append(
            {
                "name": f"video-{Path(video['path']).name}",
                "passed": bool(video.get("valid") and video.get("firstFrameClean") and video.get("lastFrameHasDrawing") and video.get("sizeBytes", 0) > 1000),
                "detail": video,
            }
        )

    # 也確認每幕輸出中沒有被寫死成「猴子」的主體設定。
    profile_text = json.dumps(project.get("subject_profile") or {}, ensure_ascii=False)
    subject_replaceable = "猴子" not in profile_text or "不可自動替換成猴子" in profile_text
    all_subjects = (project.get("subject_profile") or {}).get("subjects") or {}
    subject_replaceable = subject_replaceable and all(bool(item.get("replaceable")) for item in all_subjects.values())
    checks.append(
        {
            "name": "replaceable-subject-profile",
            "passed": subject_replaceable and len(all_subjects) >= 3,
            "detail": {"subjectIds": sorted(all_subjects), "allReplaceable": all(bool(item.get("replaceable")) for item in all_subjects.values())},
        }
    )

    passed = all(item["passed"] for item in checks)
    report = {
        "valid": passed,
        "project": str(project_file),
        "mode": "full" if full_res else "low-res",
        "ffprobeAvailable": bool(ffprobe_path()),
        "checks": checks,
        "final": str(final_output) if final_output else None,
    }
    report_path = root / "build" / "acceptance-report.json"
    dump_json(report, report_path)
    report["report"] = str(report_path)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="執行 universal-whiteboard-animation 端到端驗收")
    parser.add_argument("project", nargs="?", default="examples/demo/project.yaml")
    parser.add_argument("--full-res", action="store_true")
    args = parser.parse_args(argv)
    project_file = Path(args.project)
    if not project_file.is_absolute():
        candidate = Path.cwd() / project_file
        if candidate.exists():
            project_file = candidate
        else:
            project_file = Path(__file__).resolve().parent.parent / project_file
    if not project_file.exists() and "examples/demo" in project_file.as_posix():
        generate_demo()
    try:
        report = run(project_file, full_res=args.full_res)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    for check in report["checks"]:
        print(f"[{'ok' if check['passed'] else 'FAIL'}] {check['name']}")
    print(f"REPORT={Path(report['report']).resolve()}")
    if report["final"]:
        print(f"FINAL={Path(report['final']).resolve()}")
    print(f"VALID={str(report['valid']).lower()}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
