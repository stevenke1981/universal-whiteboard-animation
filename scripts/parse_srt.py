#!/usr/bin/env python3
"""解析 SRT / WebVTT / 純文字，並依自然斷點建立白板動畫分幕建議。"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Iterable

_TIME_RE = re.compile(
    r"(?:(?P<h>\d{1,3}):)?(?P<m>\d{1,2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})"
)
_TAG_RE = re.compile(r"<[^>]+>")
_SENTENCE_END_RE = re.compile(r"[。！？!?…]+[\"'”’）】》」』]*$")
_CLAUSE_END_RE = re.compile(r"[，、；：,;:。！？!?…]+[\"'”’）】》」』]*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?…])\s*|\n+")


def _timestamp_to_ms(value: str) -> int:
    match = _TIME_RE.search(value.strip())
    if not match:
        raise ValueError(f"無法解析時間戳: {value}")
    hours = int(match.group("h") or 0)
    minutes = int(match.group("m"))
    seconds = int(match.group("s"))
    millis = int(match.group("ms").ljust(3, "0"))
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + millis


def _clean_text(lines: Iterable[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = _TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_timed_text(text: str) -> tuple[list[dict], str, list[str]]:
    """解析 SRT 或 WebVTT；回傳 cues、格式、警告。"""
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    fmt = "webvtt" if normalized.lstrip().upper().startswith("WEBVTT") else "srt"
    if fmt == "webvtt":
        normalized = re.sub(r"^\s*WEBVTT[^\n]*\n", "", normalized, count=1, flags=re.I)

    blocks = re.split(r"\n\s*\n", normalized.strip()) if normalized.strip() else []
    cues: list[dict] = []
    warnings: list[str] = []
    for block_index, block in enumerate(blocks, start=1):
        lines = [line for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        timeline_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timeline_index is None:
            if fmt == "webvtt" and lines[0].startswith(("NOTE", "STYLE", "REGION")):
                continue
            warnings.append(f"區塊 {block_index} 沒有時間軸，已略過")
            continue
        timeline = lines[timeline_index]
        start_raw, end_raw = [part.strip().split()[0] for part in timeline.split("-->", maxsplit=1)]
        try:
            start_ms = _timestamp_to_ms(start_raw)
            end_ms = _timestamp_to_ms(end_raw)
        except ValueError as exc:
            warnings.append(f"區塊 {block_index}: {exc}")
            continue
        body = _clean_text(lines[timeline_index + 1 :])
        if not body:
            warnings.append(f"區塊 {block_index} 沒有字幕內容，已略過")
            continue
        if end_ms <= start_ms:
            warnings.append(f"區塊 {block_index} 結束時間不晚於開始時間，已略過")
            continue
        cues.append(
            {
                "index": len(cues) + 1,
                "sourceBlock": block_index,
                "startMs": start_ms,
                "endMs": end_ms,
                "durMs": end_ms - start_ms,
                "text": body,
            }
        )

    cues.sort(key=lambda item: (item["startMs"], item["endMs"]))
    for index, cue in enumerate(cues, start=1):
        cue["index"] = index
    return cues, fmt, warnings


def parse_plain_text(text: str, chars_per_second: float = 6.0) -> tuple[list[dict], list[str]]:
    normalized = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(normalized) if part.strip()]
    if not parts and normalized:
        parts = [normalized]
    cues: list[dict] = []
    cursor = 0
    warnings = ["輸入沒有時間軸，已依字數估算時間；正式成片前應以旁白或字幕重新對時。"]
    for index, part in enumerate(parts, start=1):
        seconds = max(1.2, len(part) / max(0.5, chars_per_second))
        duration = int(round(seconds * 1000))
        cues.append(
            {
                "index": index,
                "sourceBlock": index,
                "startMs": cursor,
                "endMs": cursor + duration,
                "durMs": duration,
                "text": part,
                "estimatedTiming": True,
            }
        )
        cursor += duration + 150
    return cues, warnings


def _ends_sentence(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text.strip()))


def _ends_clause(text: str) -> bool:
    return bool(_CLAUSE_END_RE.search(text.strip()))


def group_scenes(
    cues: list[dict],
    *,
    target_sec: float,
    min_sec: float,
    max_sec: float,
    prefer_punctuation: bool,
    gap_sec: float,
) -> tuple[list[dict], list[str]]:
    if not cues:
        return [], []
    if not (0 < min_sec <= target_sec <= max_sec):
        raise ValueError("必須符合 0 < min-sec <= target-sec <= max-sec")

    min_ms = int(min_sec * 1000)
    target_ms = int(target_sec * 1000)
    max_ms = int(max_sec * 1000)
    gap_ms = int(gap_sec * 1000)
    warnings: list[str] = []
    scenes: list[dict] = []
    bucket: list[dict] = []

    def flush(reason: str) -> None:
        if not bucket:
            return
        start = bucket[0]["startMs"]
        end = bucket[-1]["endMs"]
        scenes.append(
            {
                "sceneIndex": len(scenes) + 1,
                "sceneId": f"scene-{len(scenes) + 1:02d}",
                "startMs": start,
                "endMs": end,
                "sceneDurationMs": end - start,
                "cueRange": [bucket[0]["index"], bucket[-1]["index"]],
                "cueIds": [cue["index"] for cue in bucket],
                "breakReason": reason,
                "text": " ".join(cue["text"] for cue in bucket).strip(),
            }
        )
        bucket.clear()

    for i, cue in enumerate(cues):
        if bucket and cue["endMs"] - bucket[0]["startMs"] > max_ms:
            flush("max-before-next-cue")
        bucket.append(cue)
        span = bucket[-1]["endMs"] - bucket[0]["startMs"]
        next_gap = 0
        if i + 1 < len(cues):
            next_gap = max(0, cues[i + 1]["startMs"] - cue["endMs"])

        if span >= max_ms:
            flush("max-duration")
            continue
        if span < min_ms:
            continue

        natural_gap = next_gap >= gap_ms
        sentence_boundary = _ends_sentence(cue["text"])
        clause_boundary = _ends_clause(cue["text"])
        if natural_gap:
            flush("subtitle-gap")
        elif prefer_punctuation and sentence_boundary and span >= int(target_ms * 0.62):
            flush("sentence-boundary")
        elif span >= target_ms and (
            not prefer_punctuation or clause_boundary or span >= int(target_ms * 1.18)
        ):
            flush("target-duration")

    flush("end-of-input")

    # 避免最後一幕過短；在不嚴重超過上限時併回前幕。
    if len(scenes) >= 2 and scenes[-1]["sceneDurationMs"] < min_ms:
        previous = scenes[-2]
        last = scenes[-1]
        merged_span = last["endMs"] - previous["startMs"]
        if merged_span <= int(max_ms * 1.15):
            previous["endMs"] = last["endMs"]
            previous["sceneDurationMs"] = merged_span
            previous["cueRange"][1] = last["cueRange"][1]
            previous["cueIds"].extend(last["cueIds"])
            previous["text"] = f"{previous['text']} {last['text']}".strip()
            previous["breakReason"] = "merged-short-tail"
            scenes.pop()

    for index, scene in enumerate(scenes, start=1):
        scene["sceneIndex"] = index
        scene["sceneId"] = f"scene-{index:02d}"
        if scene["sceneDurationMs"] > max_ms:
            warnings.append(
                f"{scene['sceneId']} 長度 {scene['sceneDurationMs']/1000:.1f}s 超過 max-sec；"
                "可能包含單一超長字幕或為避免短尾合併。"
            )
        scene["estimatedElementCount"] = max(
            2,
            min(7, math.ceil(len(scene["text"]) / 34)),
        )
    return scenes, warnings


def build_output(
    source: Path,
    cues: list[dict],
    scenes: list[dict],
    fmt: str,
    warnings: list[str],
    args: argparse.Namespace,
) -> dict:
    total_ms = cues[-1]["endMs"] - cues[0]["startMs"] if cues else 0
    return {
        "version": 1,
        "source": str(source),
        "format": fmt,
        "metadata": {
            "cueCount": len(cues),
            "sceneCount": len(scenes),
            "totalMs": total_ms,
            "segmentation": {
                "targetSec": args.target_sec,
                "minSec": args.min_sec,
                "maxSec": args.max_sec,
                "preferPunctuation": args.prefer_punctuation,
                "gapSec": args.gap_sec,
            },
        },
        "warnings": warnings,
        "cues": cues,
        "scenes": scenes,
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="解析 SRT/WebVTT/純文字並建立自然斷點分幕")
    parser.add_argument("source", help=".srt、.vtt 或純文字檔")
    parser.add_argument("--target-sec", type=float, default=22.0)
    parser.add_argument("--min-sec", type=float, default=8.0)
    parser.add_argument("--max-sec", type=float, default=35.0)
    parser.add_argument("--gap-sec", type=float, default=1.2, help="字幕間隔達此秒數視為自然斷點")
    parser.add_argument(
        "--prefer-punctuation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="優先在句尾／子句尾分幕",
    )
    parser.add_argument("--plain-cps", type=float, default=6.0, help="純文字估時的每秒字元數")
    parser.add_argument("--output", help="JSON 輸出路徑；未指定則輸出 stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    source = Path(args.source)
    try:
        raw = source.read_text(encoding="utf-8-sig")
    except OSError as exc:
        print(f"[err] 無法讀取來源: {exc}", file=sys.stderr)
        return 2

    timed = "-->" in raw
    if timed:
        cues, fmt, warnings = parse_timed_text(raw)
    else:
        cues, warnings = parse_plain_text(raw, chars_per_second=args.plain_cps)
        fmt = "plain"
    if not cues:
        print("[err] 沒有解析到可用字幕或文字", file=sys.stderr)
        return 2

    try:
        scenes, scene_warnings = group_scenes(
            cues,
            target_sec=args.target_sec,
            min_sec=args.min_sec,
            max_sec=args.max_sec,
            prefer_punctuation=args.prefer_punctuation,
            gap_sec=args.gap_sec,
        )
    except ValueError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    warnings.extend(scene_warnings)
    result = build_output(source, cues, scenes, fmt, warnings, args)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")
        print(f"OUTPUT={target.resolve()}")
    else:
        sys.stdout.write(encoded)

    print(
        f"字幕 {len(cues)} 條，總長 {result['metadata']['totalMs']/1000:.1f}s，"
        f"建議 {len(scenes)} 幕。",
        file=sys.stderr,
    )
    for scene in scenes:
        print(
            f"  {scene['sceneId']} {scene['startMs']/1000:.1f}-{scene['endMs']/1000:.1f}s "
            f"({scene['breakReason']}): {scene['text'][:44]}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
