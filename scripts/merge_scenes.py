#!/usr/bin/env python3
"""依順序合併多幕 MP4；ffmpeg 優先，OpenCV 作無音訊回退。"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2

from common import dump_json, ffmpeg_path


def ffmpeg_concat(inputs: list[Path], output: Path) -> tuple[bool, str]:
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return False, "ffmpeg-unavailable"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        for item in inputs:
            escaped = item.resolve().as_posix().replace("'", "'\\''")
            handle.write(f"file '{escaped}'\n")
        list_file = Path(handle.name)
    try:
        copy_command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
        result = subprocess.run(copy_command, capture_output=True, text=True)
        if result.returncode == 0 and output.exists():
            return True, "ffmpeg-copy"
        encode_command = [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ]
        result = subprocess.run(encode_command, capture_output=True, text=True)
        if result.returncode == 0 and output.exists():
            return True, "ffmpeg-reencode"
        return False, result.stderr[-1000:]
    finally:
        list_file.unlink(missing_ok=True)


def opencv_concat(inputs: list[Path], output: Path) -> tuple[bool, str]:
    first = cv2.VideoCapture(str(inputs[0]))
    if not first.isOpened():
        return False, f"無法開啟 {inputs[0]}"
    width = int(first.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(first.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = first.get(cv2.CAP_PROP_FPS) or 30.0
    first.release()
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        return False, "無法建立 OpenCV VideoWriter"
    frames = 0
    try:
        for item in inputs:
            capture = cv2.VideoCapture(str(item))
            if not capture.isOpened():
                return False, f"無法開啟 {item}"
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
                writer.write(frame)
                frames += 1
            capture.release()
    finally:
        writer.release()
    return output.exists() and output.stat().st_size > 0, f"opencv-frames={frames}; audio-dropped"


def merge(inputs: list[Path], output: Path) -> dict:
    missing = [str(item) for item in inputs if not item.exists()]
    if missing:
        raise FileNotFoundError(f"缺少輸入: {', '.join(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    ok, method = ffmpeg_concat(inputs, output)
    warnings: list[str] = []
    if not ok:
        warnings.append(f"ffmpeg 合併未成功，改用 OpenCV: {method}")
        ok, method = opencv_concat(inputs, output)
    if not ok:
        raise RuntimeError(f"合併失敗: {method}")
    if method.startswith("opencv"):
        warnings.append("OpenCV 回退不保留音訊；請安裝 ffmpeg 後重新完稿。")
    return {
        "valid": True,
        "inputs": [str(item) for item in inputs],
        "output": str(output),
        "method": method,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="依順序合併白板動畫場景")
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    try:
        report = merge([Path(item) for item in args.inputs], Path(args.output))
    except (OSError, RuntimeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if args.report:
        dump_json(report, args.report)
    for warning in report["warnings"]:
        print(f"[warn] {warning}", file=sys.stderr)
    print(f"METHOD={report['method']}")
    print(f"OUTPUT={Path(report['output']).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
