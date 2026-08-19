#!/usr/bin/env python3
"""一鍵：文字／SRT → 中文拆筆 → 渲染 → 合併／mux。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from chinese_stroke_split import DEFAULT_FONT, split_scene
from finalize_video import finalize
from parse_srt import group_scenes, parse_plain_text, parse_timed_text
from render_whiteboard import RenderConfig, render


def discover_font(explicit: str | None) -> Path:
    candidates = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend(
        [
            Path(DEFAULT_FONT),
            Path(r"C:/Windows/Fonts/kaiu.ttf"),
            Path(r"C:/Windows/Fonts/msyh.ttc"),
            Path("/System/Library/Fonts/STHeiti Light.ttc"),
            Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        ]
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("找不到可用中文字型；請用 --font 指定 TTF/TTC")


def load_cues(source: Path | None, text: str | None) -> tuple[list[dict], str, list[str]]:
    if text:
        cues, warnings = parse_plain_text(text)
        return cues, "plain", warnings
    if source is None:
        raise ValueError("必須提供 --text 或 --source")
    raw = source.read_text(encoding="utf-8")
    if source.suffix.lower() in {".srt", ".vtt"}:
        return parse_timed_text(raw)
    cues, warnings = parse_plain_text(raw)
    return cues, "plain", warnings


def run_pipeline(
    *,
    source: Path | None,
    text: str | None,
    out_dir: Path,
    font: Path,
    width: int,
    height: int,
    size: int,
    fps: int,
    audio: Path | None,
    low_res: bool,
    pointer: str,
    write_stroke_previews: bool,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir = out_dir / "scenes"
    clips_dir = out_dir / "clips"
    build_dir = out_dir / "build"
    output_dir = out_dir / "output"
    for path in (scenes_dir, clips_dir, build_dir, output_dir):
        path.mkdir(parents=True, exist_ok=True)

    cues, fmt, parse_warnings = load_cues(source, text)
    if not cues:
        raise ValueError("沒有可用字幕或文字")
    scenes, group_warnings = group_scenes(
        cues,
        target_sec=8.0 if fmt == "plain" else 22.0,
        min_sec=1.2 if fmt == "plain" else 8.0,
        max_sec=20.0 if fmt == "plain" else 35.0,
        prefer_punctuation=True,
        gap_sec=1.2,
    )
    warnings = [*parse_warnings, *group_warnings]
    cfg = RenderConfig(
        fps=12 if low_res else fps,
        cap_long_edge=640 if low_res else width,
        ink_path="skeleton",
        color_fill="wipe",
        pointer=pointer,
        background="#F5EBD7",
        ink_radius=4 if low_res else 5,
        pointer_height=120 if low_res else 260,
    )

    clips: list[Path] = []
    scene_reports: list[dict] = []
    for scene in scenes:
        scene_id = scene["sceneId"]
        split = split_scene(
            text=scene["text"],
            font_path=str(font),
            size=max(72, size // 2) if low_res else size,
            width=640 if low_res else width,
            height=360 if low_res else height,
            bg="#F5EBD7",
            ink="#373737",
            padding=6 if low_res else 14,
            base_ms=220,
            ms_per_px=0.32,
            final_hold_ms=500 if low_res else 700,
            scene_id=scene_id,
            out_dir=out_dir,
            write_stroke_previews=write_stroke_previews,
        )
        clip = clips_dir / f"{scene_id}.mp4"
        render_report = render(
            Path(split["sceneImage"]),
            Path(split["annotation"]),
            clip,
            cfg,
        )
        clips.append(clip)
        scene_reports.append(
            {
                "sceneId": scene_id,
                "text": scene["text"],
                "strokes": split["strokes"],
                "clip": str(clip),
                "strokePoints": [item["strokePoints"] for item in render_report["elements"]],
            }
        )

    final = output_dir / "final.mp4"
    finalize_report = finalize(
        clips,
        final,
        audio=audio,
        subtitles=None,
        subtitle_mode="none",
        keep_intermediate=False,
    )
    report = {
        "valid": finalize_report["valid"],
        "format": fmt,
        "font": str(font),
        "scenes": scene_reports,
        "output": str(final),
        "audio": str(audio) if audio else None,
        "warnings": [*warnings, *finalize_report.get("warnings", [])],
    }
    (build_dir / "pipeline-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="一鍵產出中文白板書寫影片")
    parser.add_argument("--source", help="SRT / VTT / 純文字檔")
    parser.add_argument("--text", help="直接傳入要書寫的中文")
    parser.add_argument("--out-dir", default=".")
    parser.add_argument("--font")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--size", type=int, default=220)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--audio", help="可選旁白／音樂，ffmpeg 可用時 mux")
    parser.add_argument("--pointer", choices=["pen", "circle", "none"], default="pen")
    parser.add_argument("--low-res", action="store_true", help="640x360 預覽")
    parser.add_argument("--no-stroke-previews", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_pipeline(
            source=Path(args.source) if args.source else None,
            text=args.text,
            out_dir=Path(args.out_dir),
            font=discover_font(args.font),
            width=args.width,
            height=args.height,
            size=args.size,
            fps=args.fps,
            audio=Path(args.audio) if args.audio else None,
            low_res=args.low_res,
            pointer=args.pointer,
            write_stroke_previews=not args.no_stroke_previews,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
