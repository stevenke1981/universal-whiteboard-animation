#!/usr/bin/env python3
"""中文字逐字筆畫資料模型與本機資料來源載入器。"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StrokeDataError(ValueError):
    """筆畫資料缺失、格式錯誤或無法解析。"""


@dataclass(frozen=True)
class CharacterStrokeData:
    character: str
    strokes: tuple[str, ...]
    medians: tuple[tuple[tuple[float, float], ...], ...]
    source: str

    @classmethod
    def from_mapping(cls, character: str, raw: dict[str, Any], source: str) -> "CharacterStrokeData":
        strokes_raw = raw.get("strokes")
        medians_raw = raw.get("medians")
        if not isinstance(strokes_raw, list) or not strokes_raw:
            raise StrokeDataError(f"{character!r} 沒有有效 strokes: {source}")
        if not isinstance(medians_raw, list) or len(medians_raw) != len(strokes_raw):
            raise StrokeDataError(
                f"{character!r} 的 medians 數量必須與 strokes 相同: {source}"
            )

        strokes: list[str] = []
        medians: list[tuple[tuple[float, float], ...]] = []
        for index, stroke in enumerate(strokes_raw, start=1):
            if not isinstance(stroke, str) or not stroke.strip():
                raise StrokeDataError(f"{character!r} 第 {index} 筆 SVG path 無效: {source}")
            median_raw = medians_raw[index - 1]
            if not isinstance(median_raw, list) or len(median_raw) < 2:
                raise StrokeDataError(f"{character!r} 第 {index} 筆 median 至少需要 2 點: {source}")
            points: list[tuple[float, float]] = []
            for point in median_raw:
                if (
                    not isinstance(point, (list, tuple))
                    or len(point) != 2
                    or not all(isinstance(value, (int, float)) for value in point)
                ):
                    raise StrokeDataError(
                        f"{character!r} 第 {index} 筆 median 點格式錯誤: {point!r}"
                    )
                points.append((float(point[0]), float(point[1])))
            strokes.append(stroke.strip())
            medians.append(tuple(points))
        return cls(character, tuple(strokes), tuple(medians), source)


class StrokeDataRepository:
    """從目錄、單一 JSON 或 JSONL 查詢中文字筆畫資料。"""

    def __init__(self, source: str | Path | None):
        self.source = Path(source).expanduser().resolve() if source else None
        self._cache: dict[str, CharacterStrokeData | None] = {}
        self._json_payload: Any = None
        self._jsonl_cache: dict[str, dict[str, Any]] | None = None

    @staticmethod
    def discover(*roots: str | Path) -> Path | None:
        """依環境變數與常見資料夾尋找本機筆畫資料。"""
        candidates: list[Path] = []
        env = os.environ.get("HANZI_WRITER_DATA_DIR") or os.environ.get("CHINESE_STROKE_DATA")
        if env:
            candidates.append(Path(env).expanduser())
        for root in roots:
            base = Path(root).expanduser()
            candidates.extend(
                [
                    base / "assets" / "chinese-strokes",
                    base / "assets" / "hanzi-writer-data",
                    base / "node_modules" / "hanzi-writer-data",
                    base / "graphics.txt",
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return candidate.resolve()
        return None

    def get(self, character: str) -> CharacterStrokeData | None:
        if character in self._cache:
            return self._cache[character]
        if self.source is None:
            self._cache[character] = None
            return None
        try:
            if self.source.is_dir():
                raw, source_label = self._read_directory(character)
            elif self.source.is_file():
                raw, source_label = self._read_file(character)
            else:
                raise StrokeDataError(f"筆畫資料路徑不存在: {self.source}")
            result = (
                CharacterStrokeData.from_mapping(character, raw, source_label)
                if raw is not None
                else None
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise StrokeDataError(f"讀取筆畫資料失敗 {self.source}: {exc}") from exc
        self._cache[character] = result
        return result

    def _read_directory(self, character: str) -> tuple[dict[str, Any] | None, str]:
        assert self.source is not None
        codepoint = ord(character)
        names = [
            f"{character}.json",
            f"{codepoint}.json",
            f"{codepoint:x}.json",
            f"{codepoint:X}.json",
            f"U+{codepoint:04X}.json",
        ]
        roots = [self.source, self.source / "data"]
        for root in roots:
            for name in names:
                candidate = root / name
                if candidate.is_file():
                    raw = json.loads(candidate.read_text(encoding="utf-8-sig"))
                    if not isinstance(raw, dict):
                        raise StrokeDataError(f"逐字 JSON 根節點必須是 object: {candidate}")
                    return raw, str(candidate)
        return None, str(self.source)

    def _read_file(self, character: str) -> tuple[dict[str, Any] | None, str]:
        assert self.source is not None
        suffix = self.source.suffix.lower()
        if suffix in {".txt", ".jsonl", ".ndjson"}:
            if self._jsonl_cache is None:
                self._jsonl_cache = {}
                with self.source.open("r", encoding="utf-8-sig") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        stripped = line.strip()
                        if not stripped:
                            continue
                        try:
                            raw = json.loads(stripped)
                        except json.JSONDecodeError as exc:
                            raise StrokeDataError(
                                f"JSONL 第 {line_number} 行格式錯誤: {self.source}: {exc}"
                            ) from exc
                        if isinstance(raw, dict) and isinstance(raw.get("character"), str):
                            self._jsonl_cache[raw["character"]] = raw
            return self._jsonl_cache.get(character), str(self.source)

        if self._json_payload is None:
            self._json_payload = json.loads(self.source.read_text(encoding="utf-8-sig"))
        payload = self._json_payload
        if isinstance(payload, dict):
            if "strokes" in payload and "medians" in payload:
                payload_character = payload.get("character")
                if payload_character in (None, character):
                    return payload, str(self.source)
                return None, str(self.source)
            candidate = payload.get(character)
            if isinstance(candidate, dict):
                return candidate, str(self.source)
            data = payload.get("data")
            if isinstance(data, dict) and isinstance(data.get(character), dict):
                return data[character], str(self.source)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict) and item.get("character") == character:
                    return item, str(self.source)
        return None, str(self.source)
