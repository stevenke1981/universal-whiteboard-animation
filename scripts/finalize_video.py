#!/usr/bin/env python3
"""合併場景並選擇性加入旁白、背景音訊與 soft/burn subtitles。"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import dump_json, ffmpeg_path
from merge_scenes import merge


def _escape_subtitle_path(path: Path) -> str:
    # ffmpeg filter path：反斜線與冒號都需跳脫。
    value = path.resolve().as_posix().replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return value


def add_audio(video: Path, audio: Path, output: Path) -> tuple[bool, str]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg-unavailable"
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-i",
        str(audio),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0 and output.exists(), result.stderr[-1000:]


def add_soft_subtitles(video: Path, subtitles: Path, output: Path) -> tuple[bool, str]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg-unavailable"
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-i",
        str(subtitles),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-map",
        "1:0",
        "-c:v",
        "copy",
        "-c:a",
        "copy",
        "-c:s",
        "mov_text",
        "-metadata:s:s:0",
        "language=zho",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0 and output.exists(), result.stderr[-1000:]


def burn_subtitles(video: Path, subtitles: Path, output: Path) -> tuple[bool, str]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg-unavailable"
    escaped = _escape_subtitle_path(subtitles)
    filter_value = f"subtitles=filename='{escaped}'"
    command = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(video),
        "-vf",
        filter_value,
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        "-movflags",
        "+faststart",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    return result.returncode == 0 and output.exists(), result.stderr[-1000:]


def finalize(
    inputs: list[Path],
    output: Path,
    *,
    audio: Path | None,
    subtitles: Path | None,
    subtitle_mode: str,
    keep_intermediate: bool,
) -> dict:
    if audio and not audio.exists():
        raise FileNotFoundError(audio)
    if subtitles and not subtitles.exists():
        raise FileNotFoundError(subtitles)
    output.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    intermediates: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="whiteboard-finalize-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        merged = temp_dir / "merged.mp4"
        merge_report = merge(inputs, merged)
        warnings.extend(merge_report["warnings"])
        current = merged

        if audio is not None:
            audio_muxed = temp_dir / "with-audio.mp4"
            ok, detail = add_audio(current, audio, audio_muxed)
            if ok:
                current = audio_muxed
            else:
                warnings.append(f"音訊未加入: {detail}")

        if subtitles is not None and subtitle_mode != "none":
            subtitled = temp_dir / "with-subtitles.mp4"
            if subtitle_mode == "soft":
                ok, detail = add_soft_subtitles(current, subtitles, subtitled)
            else:
                ok, detail = burn_subtitles(current, subtitles, subtitled)
            if ok:
                current = subtitled
            else:
                warnings.append(f"字幕未加入: {detail}")

        output.unlink(missing_ok=True)
        shutil.copy2(current, output)
        if keep_intermediate:
            intermediate_dir = output.parent / f"{output.stem}-intermediate"
            intermediate_dir.mkdir(parents=True, exist_ok=True)
            for item in temp_dir.glob("*.mp4"):
                target = intermediate_dir / item.name
                shutil.copy2(item, target)
                intermediates.append(target)

    return {
        "valid": output.exists() and output.stat().st_size > 0,
        "inputs": [str(item) for item in inputs],
        "output": str(output),
        "audio": str(audio) if audio else None,
        "subtitles": str(subtitles) if subtitles else None,
        "subtitleMode": subtitle_mode,
        "intermediates": [str(item) for item in intermediates],
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="白板動畫多幕、音訊與字幕完稿")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--audio")
    parser.add_argument("--subtitles")
    parser.add_argument("--subtitle-mode", choices=["none", "soft", "burn"], default="none")
    parser.add_argument("--keep-intermediate", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    try:
        report = finalize(
            [Path(item) for item in args.inputs],
            Path(args.output),
            audio=Path(args.audio) if args.audio else None,
            subtitles=Path(args.subtitles) if args.subtitles else None,
            subtitle_mode=args.subtitle_mode,
            keep_intermediate=args.keep_intermediate,
        )
    except (OSError, RuntimeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if args.report:
        dump_json(report, args.report)
    for warning in report["warnings"]:
        print(f"[warn] {warning}", file=sys.stderr)
    print(f"OUTPUT={Path(report['output']).resolve()}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
