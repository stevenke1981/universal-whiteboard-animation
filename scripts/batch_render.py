#!/usr/bin/env python3
"""依 project.yaml 驗證、預覽、渲染全部場景並完稿。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from common import dump_json, load_yaml, resolve_project_path
from finalize_video import finalize
from render_annotation_preview import render_preview
from render_whiteboard import RenderConfig, render
from validate_annotation import validate

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


def discover_scenes(project_file: Path, project: dict) -> list[dict]:
    scenes = [dict(item) for item in project.get("scenes") or []]
    if scenes and any(item.get("annotation") for item in scenes):
        return scenes
    scenes_dir = resolve_project_path(project_file, (project.get("paths") or {}).get("scenes", "scenes"))
    if scenes_dir is None or not scenes_dir.exists():
        return scenes
    discovered: list[dict] = []
    for annotation in sorted(scenes_dir.glob("*.annotation.json")):
        stem = annotation.name[: -len(".annotation.json")]
        image = next((annotation.with_name(stem + ext) for ext in IMAGE_EXTENSIONS if annotation.with_name(stem + ext).exists()), None)
        if image is None:
            continue
        discovered.append(
            {
                "scene_id": stem.split("-")[0] + "-" + stem.split("-")[1] if stem.startswith("scene-") else stem,
                "image": str(image.relative_to(project_file.parent)),
                "annotation": str(annotation.relative_to(project_file.parent)),
                "output": None,
            }
        )
    return discovered


def _build_config(project: dict, project_file: Path, low_res: bool) -> RenderConfig:
    canvas = project.get("canvas") or {}
    settings = project.get("render") or {}
    ratio = settings.get("ink_color_ratio") or [2, 1]
    pointer_image_value = settings.get("pointer_image")
    pointer_image = resolve_project_path(project_file, pointer_image_value) if pointer_image_value else None
    return RenderConfig(
        fps=15 if low_res else int(canvas.get("fps", 30)),
        cap_long_edge=640 if low_res else int(settings.get("cap_long_edge", 1080)),
        grid_edge=int(settings.get("grid_edge", 10)),
        ink_path=str(settings.get("ink_path", "skeleton")),
        color_fill=str(settings.get("color_fill", "wipe")),
        pointer=str(settings.get("pointer", "pen")),
        pointer_image=pointer_image,
        pointer_height=int(settings.get("pointer_height", 260)),
        pointer_anchor_x=float(settings.get("pointer_anchor_x", 0.05)),
        pointer_anchor_y=float(settings.get("pointer_anchor_y", 0.92)),
        background=str(canvas.get("background", "#F5EBD7")),
        content_threshold=int(settings.get("content_threshold", 30)),
        ink_threshold=int(settings.get("ink_threshold", 55)),
        ink_radius=int(settings.get("ink_radius", 5)),
        brush_radius=int(settings.get("brush_radius", 42)),
        ink_weight=int(ratio[0] if len(ratio) > 0 else 2),
        color_weight=int(ratio[1] if len(ratio) > 1 else 1),
        mask_policy_override=settings.get("mask_policy"),
        finalize_mode=str(settings.get("finalize_mode", "union-only")),
        final_fade_ms=int(settings.get("final_fade_ms", 450)),
        keep_raw=bool(settings.get("keep_raw", False)),
    )


def batch_render(
    project_file: Path,
    *,
    low_res: bool,
    no_finalize: bool,
    continue_on_error: bool,
    only: set[str] | None,
) -> dict:
    project = load_yaml(project_file)
    project_root = project_file.resolve().parent
    paths = project.get("paths") or {}
    build_dir = resolve_project_path(project_file, paths.get("build", "build")) or project_root / "build"
    output_dir = resolve_project_path(project_file, paths.get("output", "output")) or project_root / "output"
    validation_dir = build_dir / "validation"
    preview_dir = build_dir / "previews"
    for directory in (validation_dir, preview_dir, output_dir):
        directory.mkdir(parents=True, exist_ok=True)

    scenes = discover_scenes(project_file, project)
    if only:
        scenes = [scene for scene in scenes if str(scene.get("scene_id")) in only]
    if not scenes:
        raise ValueError("project.yaml 沒有可渲染場景，也未在 scenes 目錄找到同名圖片與標注")

    cfg = _build_config(project, project_file, low_res)
    scene_reports: list[dict] = []
    outputs: list[Path] = []
    errors: list[str] = []

    for index, scene in enumerate(scenes, start=1):
        scene_id = str(scene.get("scene_id") or f"scene-{index:02d}")
        image = resolve_project_path(project_file, scene.get("image"))
        annotation = resolve_project_path(project_file, scene.get("annotation"))
        if image is None or annotation is None:
            message = f"{scene_id}: image/annotation 尚未設定"
            errors.append(message)
            if continue_on_error:
                continue
            raise ValueError(message)
        output_value = scene.get("output") or f"{paths.get('output', 'output')}/{scene_id}.mp4"
        output = resolve_project_path(project_file, output_value) or output_dir / f"{scene_id}.mp4"
        validation_report_path = validation_dir / f"{scene_id}.json"
        preview_path = preview_dir / f"{scene_id}.png"
        render_report_path = build_dir / f"{scene_id}.render.json"

        print(f"[{index}/{len(scenes)}] {scene_id}: validate")
        validation = validate(image, annotation)
        dump_json(validation, validation_report_path)
        if not validation["valid"]:
            message = f"{scene_id}: annotation 驗證失敗 ({validation['summary']['errors']} errors)"
            errors.append(message)
            if continue_on_error:
                scene_reports.append({"sceneId": scene_id, "valid": False, "validation": validation})
                continue
            raise ValueError(message)

        print(f"[{index}/{len(scenes)}] {scene_id}: preview")
        render_preview(image, annotation, preview_path)
        print(f"[{index}/{len(scenes)}] {scene_id}: render")
        render_report = render(image, annotation, output, cfg, report_path=render_report_path)
        outputs.append(Path(render_report["output"]))
        scene_reports.append(
            {
                "sceneId": scene_id,
                "valid": True,
                "image": str(image),
                "annotation": str(annotation),
                "preview": str(preview_path),
                "output": render_report["output"],
                "validation": validation["summary"],
                "render": render_report,
            }
        )

    final_report = None
    if outputs and not no_finalize and bool((project.get("finalize") or {}).get("merge", True)):
        finalize_cfg = project.get("finalize") or {}
        final_output_value = finalize_cfg.get("output") or f"{paths.get('output', 'output')}/final.mp4"
        final_output = resolve_project_path(project_file, final_output_value) or output_dir / "final.mp4"
        audio_value = finalize_cfg.get("audio") or (project.get("input") or {}).get("audio")
        subtitle_mode = str(finalize_cfg.get("subtitle_mode", "none"))
        subtitles_value = finalize_cfg.get("subtitles")
        if not subtitles_value and subtitle_mode != "none":
            subtitles_value = (project.get("input") or {}).get("subtitles")
        audio = resolve_project_path(project_file, audio_value) if audio_value else None
        subtitles = resolve_project_path(project_file, subtitles_value) if subtitles_value else None
        print(f"[finalize] {len(outputs)} scenes -> {final_output}")
        final_report = finalize(
            outputs,
            final_output,
            audio=audio,
            subtitles=subtitles,
            subtitle_mode=subtitle_mode,
            keep_intermediate=bool(finalize_cfg.get("keep_intermediate", False)),
        )

    report = {
        "valid": not errors and all(item.get("valid") for item in scene_reports),
        "project": str(project_file),
        "mode": "low-res" if low_res else "full",
        "scenes": scene_reports,
        "outputs": [str(item) for item in outputs],
        "final": final_report,
        "errors": errors,
    }
    dump_json(report, build_dir / "batch-report.json")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批次渲染 universal-whiteboard-animation 專案")
    parser.add_argument("project")
    parser.add_argument("--low-res", action="store_true")
    parser.add_argument("--no-finalize", action="store_true")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--only", nargs="*", help="只渲染指定 scene_id")
    args = parser.parse_args(argv)
    try:
        report = batch_render(
            Path(args.project),
            low_res=args.low_res,
            no_finalize=args.no_finalize,
            continue_on_error=args.continue_on_error,
            only=set(args.only) if args.only else None,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if report["final"]:
        print(f"FINAL={Path(report['final']['output']).resolve()}")
    print(f"VALID={str(report['valid']).lower()}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
