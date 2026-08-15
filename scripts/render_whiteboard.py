#!/usr/bin/env python3
"""Compatibility dispatcher for generic and Chinese handwriting scenes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from render_whiteboard_base import *  # noqa: F401,F403
from render_whiteboard_base import main as _base_main
from chinese_whiteboard_renderer import main as _chinese_main


def _uses_chinese_write_mode(argv: list[str]) -> bool:
    if len(argv) < 2:
        return False
    try:
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return any(
        element.get("type") in {"text-stroke", "text-glyph"}
        or (element.get("reveal") or {}).get("mode") == "write"
        for element in data.get("elements") or []
    )


def main(argv: list[str] | None = None) -> int:
    actual = list(sys.argv[1:] if argv is None else argv)
    return _chinese_main(actual) if _uses_chinese_write_mode(actual) else _base_main(actual)


if __name__ == "__main__":
    raise SystemExit(main())
