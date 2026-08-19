#!/usr/bin/env python3
"""建立 Skill 專用虛擬環境並安裝 requirements.txt。"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
VENV_ROOT = SKILL_ROOT / ".venv"
REQUIREMENTS = SKILL_ROOT / "requirements.txt"
REQUIRED_IMPORTS = ("cv2", "numpy", "PIL", "yaml", "jsonschema", "freetype", "fontTools")


def interpreter_path(root: Path) -> Path:
    if sys.platform.startswith("win"):
        return root / "Scripts" / "python.exe"
    return root / "bin" / "python"


def can_import(python: Path, module: str) -> bool:
    result = subprocess.run([str(python), "-c", f"import {module}"], capture_output=True)
    return result.returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="準備 universal-whiteboard-animation 執行環境")
    parser.add_argument("--check", action="store_true", help="只檢查，不建立或安裝")
    parser.add_argument("--venv", default=str(VENV_ROOT), help="虛擬環境路徑")
    parser.add_argument("--upgrade-pip", action="store_true")
    args = parser.parse_args(argv)

    root = Path(args.venv).expanduser().resolve()
    python = interpreter_path(root)
    if not python.exists():
        if args.check:
            print(f"[err] 尚未建立虛擬環境: {root}")
            return 1
        print(f"[..] 建立虛擬環境: {root}")
        venv.create(root, with_pip=True)

    if args.upgrade_pip and not args.check:
        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip"], check=True)

    missing = [module for module in REQUIRED_IMPORTS if not can_import(python, module)]
    if missing:
        print(f"[miss] 缺少模組: {', '.join(missing)}")
        if args.check:
            return 1
        command = [str(python), "-m", "pip", "install", "-r", str(REQUIREMENTS)]
        print(f"[..] 安裝依賴: {REQUIREMENTS}")
        result = subprocess.run(command)
        if result.returncode != 0:
            return result.returncode

    missing_after = [module for module in REQUIRED_IMPORTS if not can_import(python, module)]
    if missing_after:
        print(f"[err] 安裝後仍缺少: {', '.join(missing_after)}")
        return 1

    ffmpeg = shutil.which("ffmpeg")
    print(f"[ok] Python: {python}")
    print(f"[{'ok' if ffmpeg else 'warn'}] ffmpeg: {ffmpeg or '未找到；仍可輸出基本 MP4'}")
    print(f"ENV_PY={python}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
