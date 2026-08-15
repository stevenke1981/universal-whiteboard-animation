#!/usr/bin/env python3
"""新增、更新或替換 project.yaml 的主體，並同步場景與 annotation subjectIds。"""
from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from common import dump_json, dump_yaml, load_json, load_yaml, resolve_project_path

MODES = ("none", "single", "ensemble", "object", "concept", "adaptive")


def parse_value(raw: str) -> Any:
    """KEY=VALUE 的 VALUE 支援 JSON；無法解析時保留字串。"""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def parse_pairs(items: list[str] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"appearance 必須使用 KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"appearance key 不可空白: {item}")
        result[key] = parse_value(value.strip())
    return result


def replace_ids(items: list[str] | None, old_id: str, new_id: str) -> list[str]:
    result: list[str] = []
    for value in items or []:
        candidate = new_id if value == old_id else value
        if candidate not in result:
            result.append(candidate)
    return result


def update_subject(
    project_file: Path,
    *,
    subject_id: str | None,
    replace_id: str | None,
    mode: str | None,
    name: str | None,
    kind: str | None,
    appearance: dict[str, Any],
    identity_lock: list[str] | None,
    negative_constraints: list[str] | None,
    replaceable: bool | None,
    set_default: bool,
    remove: bool,
    update_annotations: bool,
    dry_run: bool,
    backup: bool,
) -> dict:
    project_file = project_file.resolve()
    project = load_yaml(project_file)
    original = copy.deepcopy(project)
    profile = project.setdefault("subject_profile", {"mode": "adaptive", "default_id": None, "subjects": {}})
    subjects = profile.setdefault("subjects", {})
    changed_annotations: list[str] = []
    warnings: list[str] = []

    if mode:
        profile["mode"] = mode
    if mode == "none" and subject_id is None and replace_id is None:
        profile["default_id"] = None
        profile["subjects"] = {}
        for scene in project.get("scenes") or []:
            scene["subject_bindings"] = []
        subject_id = None

    if remove:
        target = replace_id or subject_id
        if not target:
            raise ValueError("--remove 需要 --id 或 --replace-id")
        subjects.pop(target, None)
        if profile.get("default_id") == target:
            profile["default_id"] = None
        for scene in project.get("scenes") or []:
            scene["subject_bindings"] = [item for item in scene.get("subject_bindings") or [] if item != target]
        new_id = ""
    else:
        if not subject_id:
            if mode == "none":
                new_id = ""
            else:
                raise ValueError("新增或替換主體需要 --id")
        else:
            new_id = subject_id
            base: dict[str, Any] = {}
            if replace_id and replace_id in subjects:
                base = copy.deepcopy(subjects[replace_id])
            elif subject_id in subjects:
                base = copy.deepcopy(subjects[subject_id])
            base.setdefault("kind", kind or "object")
            base.setdefault("name", name or subject_id)
            base.setdefault("replaceable", True)
            base.setdefault("appearance", {})
            base.setdefault("identity_lock", [])
            base.setdefault("negative_constraints", [])
            if kind is not None:
                base["kind"] = kind
            if name is not None:
                base["name"] = name
            if replaceable is not None:
                base["replaceable"] = replaceable
            base["appearance"].update(appearance)
            if identity_lock is not None:
                base["identity_lock"] = identity_lock
            if negative_constraints is not None:
                base["negative_constraints"] = negative_constraints
            subjects[subject_id] = base
            if replace_id and replace_id != subject_id:
                subjects.pop(replace_id, None)
                if profile.get("default_id") == replace_id:
                    profile["default_id"] = subject_id
                for scene in project.get("scenes") or []:
                    scene["subject_bindings"] = replace_ids(scene.get("subject_bindings"), replace_id, subject_id)
            if set_default:
                profile["default_id"] = subject_id

    target_to_remove = replace_id or (subject_id if remove else None)
    if update_annotations and target_to_remove:
        for scene in project.get("scenes") or []:
            annotation_value = scene.get("annotation")
            if not annotation_value:
                continue
            annotation_path = resolve_project_path(project_file, annotation_value)
            if annotation_path is None or not annotation_path.exists():
                warnings.append(f"找不到 annotation，未同步: {annotation_path}")
                continue
            annotation = load_json(annotation_path)
            changed = False
            for element in annotation.get("elements") or []:
                current = element.get("subjectIds") or []
                if remove:
                    updated = [item for item in current if item != target_to_remove]
                else:
                    updated = replace_ids(current, target_to_remove, new_id)
                if updated != current:
                    element["subjectIds"] = updated
                    changed = True
            if changed:
                changed_annotations.append(str(annotation_path))
                if not dry_run:
                    if backup:
                        backup_path = annotation_path.with_suffix(annotation_path.suffix + ".bak")
                        if not backup_path.exists():
                            shutil.copy2(annotation_path, backup_path)
                    dump_json(annotation, annotation_path)

    changed = project != original
    if changed and not dry_run:
        if backup:
            backup_path = project_file.with_suffix(project_file.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(project_file, backup_path)
        dump_yaml(project, project_file)

    return {
        "valid": True,
        "changed": changed,
        "dryRun": dry_run,
        "project": str(project_file),
        "mode": profile.get("mode"),
        "defaultId": profile.get("default_id"),
        "subjectIds": sorted(subjects),
        "changedAnnotations": changed_annotations,
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="設定或替換白板動畫專案主體")
    parser.add_argument("project", help="project.yaml")
    parser.add_argument("--id", dest="subject_id", help="新主體 ID")
    parser.add_argument("--replace-id", help="要被替換的舊 ID；會同步 scene bindings 與 annotation subjectIds")
    parser.add_argument("--mode", choices=MODES)
    parser.add_argument("--name")
    parser.add_argument("--kind")
    parser.add_argument("--appearance", action="append", metavar="KEY=VALUE", help="可重複；VALUE 支援 JSON")
    parser.add_argument("--identity-lock", nargs="*")
    parser.add_argument("--negative", nargs="*", dest="negative_constraints")
    replaceable = parser.add_mutually_exclusive_group()
    replaceable.add_argument("--replaceable", action="store_true", dest="replaceable")
    replaceable.add_argument("--fixed", action="store_false", dest="replaceable")
    parser.set_defaults(replaceable=None)
    parser.add_argument("--set-default", action="store_true")
    parser.add_argument("--remove", action="store_true")
    parser.add_argument("--no-update-annotations", action="store_true")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report")
    args = parser.parse_args(argv)
    try:
        report = update_subject(
            Path(args.project),
            subject_id=args.subject_id,
            replace_id=args.replace_id,
            mode=args.mode,
            name=args.name,
            kind=args.kind,
            appearance=parse_pairs(args.appearance),
            identity_lock=args.identity_lock,
            negative_constraints=args.negative_constraints,
            replaceable=args.replaceable,
            set_default=args.set_default,
            remove=args.remove,
            update_annotations=not args.no_update_annotations,
            dry_run=args.dry_run,
            backup=args.backup,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2
    if args.report:
        dump_json(report, args.report)
    for warning in report["warnings"]:
        print(f"[warn] {warning}", file=sys.stderr)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"CHANGED={str(report['changed']).lower()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
