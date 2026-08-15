from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML 根節點必須是 object: {source}")
    return data


def dump_yaml(data: Any, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False, width=110),
        encoding="utf-8",
    )


def load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根節點必須是 object: {source}")
    return data


def dump_json(data: Any, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_project_path(project_file: str | Path, value: str | None) -> Path | None:
    if value is None or value == "":
        return None
    p = Path(value).expanduser()
    if p.is_absolute():
        return p
    return Path(project_file).resolve().parent / p


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def run_checked(command: list[str], *, quiet: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        joined = " ".join(command)
        raise RuntimeError(
            f"命令失敗 ({result.returncode}): {joined}\n"
            f"stdout:\n{result.stdout[-2000:]}\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )
    if not quiet and result.stdout.strip():
        print(result.stdout.rstrip())
    return result
