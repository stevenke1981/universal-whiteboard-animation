#!/usr/bin/env python3
"""驗證 project.yaml 與引用路徑。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import jsonschema

from common import dump_json, load_yaml, resolve_project_path

SKILL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((SKILL_ROOT / "schemas" / "project.schema.json").read_text(encoding="utf-8"))


def validate_project(project_file: Path) -> dict:
    data = load_yaml(project_file)
    issues: list[dict] = []
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for error in sorted(validator.iter_errors(data), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "root"
        issues.append({"level": "error", "code": "schema", "message": f"{location}: {error.message}"})

    for index, scene in enumerate(data.get("scenes") or []):
        scene_id = scene.get("scene_id") or f"index-{index}"
        for key in ("image", "annotation"):
            value = scene.get(key)
            if value:
                path = resolve_project_path(project_file, value)
                if path is not None and not path.exists():
                    issues.append(
                        {
                            "level": "error",
                            "code": "missing-path",
                            "message": f"{scene_id}.{key} 找不到: {path}",
                        }
                    )
    errors = [item for item in issues if item["level"] == "error"]
    return {"valid": not errors, "project": str(project_file), "issues": issues}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驗證白板動畫 project.yaml")
    parser.add_argument("project")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    try:
        report = validate_project(Path(args.project))
    except (OSError, ValueError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if args.report:
        dump_json(report, args.report)
    for item in report["issues"]:
        print(f"[{item['level']}] {item['code']}: {item['message']}")
    print(f"VALID={str(report['valid']).lower()}")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
