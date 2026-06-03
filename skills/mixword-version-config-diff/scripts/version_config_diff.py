#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List


DATASET_SPECS = {
    "LevelData": "mixword/mixword/Assets/Game/Levels/Resources/LevelData",
    "SpecialLevelData": "mixword/mixword/Assets/Game/Levels/Resources/SpecialLevelData",
    "common_normal": "common/normal",
    "common_bonus": "common/bonus",
}


@dataclass(frozen=True)
class FileRecord:
    rel_path: str
    sha256: str
    size: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_json_files(root: Path) -> Dict[str, FileRecord]:
    if not root.exists():
        return {}
    records: Dict[str, FileRecord] = {}
    for path in sorted(root.rglob("*.json")):
        rel_path = path.relative_to(root).as_posix()
        records[rel_path] = FileRecord(
            rel_path=rel_path,
            sha256=sha256_file(path),
            size=path.stat().st_size,
        )
    return records


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_records(src_root: Path, dst_root: Path, records: Iterable[FileRecord]) -> None:
    for record in records:
        src = src_root / record.rel_path
        dst = dst_root / record.rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def manifest_dict(project_root: Path, version: str, baseline_dir: Path, datasets: Dict[str, Dict[str, FileRecord]]) -> dict:
    return {
        "version": version,
        "project_root": str(project_root),
        "baseline_dir": str(baseline_dir),
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "datasets": {
            name: {
                "file_count": len(records),
                "files": [
                    {
                        "path": record.rel_path,
                        "sha256": record.sha256,
                        "size": record.size,
                    }
                    for record in records.values()
                ],
            }
            for name, records in datasets.items()
        },
    }


def resolve_dataset_specs(dataset_specs: List[str] | None) -> Dict[str, str]:
    if not dataset_specs:
        return DATASET_SPECS
    resolved: Dict[str, str] = {}
    for item in dataset_specs:
        if "=" not in item:
            raise ValueError(f"Invalid dataset spec {item!r}, expected name=relative/path")
        name, rel_dir = item.split("=", 1)
        name = name.strip()
        rel_dir = rel_dir.strip()
        if not name or not rel_dir:
            raise ValueError(f"Invalid dataset spec {item!r}, expected name=relative/path")
        resolved[name] = rel_dir
    return resolved


def default_baseline_dir(project_root: Path, version: str, baseline_root: Path | None) -> Path:
    root = baseline_root or Path.home() / ".qa-codex-skill-data" / "config-baselines"
    return root / project_root.name / version


def save_baseline(project_root: Path, version: str, baseline_root: Path | None, dataset_specs: Dict[str, str]) -> int:
    baseline_dir = default_baseline_dir(project_root, version, baseline_root)
    baseline_dir.mkdir(parents=True, exist_ok=True)

    datasets: Dict[str, Dict[str, FileRecord]] = {}
    for dataset_name, rel_dir in dataset_specs.items():
        src_root = project_root / rel_dir
        records = collect_json_files(src_root)
        datasets[dataset_name] = records
        dst_root = baseline_dir / dataset_name
        ensure_clean_dir(dst_root)
        copy_records(src_root, dst_root, records.values())

    manifest_path = baseline_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest_dict(project_root, version, baseline_dir, datasets), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Saved baseline: {baseline_dir}")
    for dataset_name, records in datasets.items():
        print(f"  {dataset_name}: {len(records)} files")
    print(f"  manifest: {manifest_path}")
    return 0


def load_manifest(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def dataset_report(current: Dict[str, FileRecord], baseline: Dict[str, FileRecord]) -> dict:
    current_keys = set(current)
    baseline_keys = set(baseline)
    added = sorted(current_keys - baseline_keys)
    removed = sorted(baseline_keys - current_keys)
    changed = sorted(
        key for key in current_keys & baseline_keys if current[key].sha256 != baseline[key].sha256
    )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed),
        },
    }


def diff_baseline(
    project_root: Path,
    version: str,
    baseline_root: Path | None,
    report_json: Path | None,
    dataset_specs: Dict[str, str],
) -> int:
    baseline_dir = default_baseline_dir(project_root, version, baseline_root)
    manifest = load_manifest(baseline_dir / "manifest.json")

    report = {
        "version": version,
        "project_root": str(project_root),
        "baseline_dir": str(baseline_dir),
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "datasets": {},
    }

    has_diff = False
    for dataset_name, rel_dir in dataset_specs.items():
        current_records = collect_json_files(project_root / rel_dir)
        baseline_records = {
            item["path"]: FileRecord(
                rel_path=item["path"],
                sha256=item["sha256"],
                size=item["size"],
            )
            for item in manifest.get("datasets", {}).get(dataset_name, {}).get("files", [])
        }
        ds_report = dataset_report(current_records, baseline_records)
        report["datasets"][dataset_name] = ds_report
        if any(ds_report["counts"].values()):
            has_diff = True

    if report_json:
        report_json.parent.mkdir(parents=True, exist_ok=True)
        report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Baseline version: {version}")
    print(f"Baseline dir: {baseline_dir}")
    print(f"Project root: {project_root}")
    for dataset_name, ds_report in report["datasets"].items():
        counts = ds_report["counts"]
        print(
            f"[{dataset_name}] added={counts['added']} removed={counts['removed']} changed={counts['changed']}"
        )
        for bucket in ("added", "removed", "changed"):
            for rel_path in ds_report[bucket]:
                print(f"  {bucket}: {rel_path}")
    if report_json:
        print(f"JSON report: {report_json}")
    return 1 if has_diff else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save and diff Mixword/gpMixWord release config baselines.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save_parser = subparsers.add_parser("save-baseline", help="Save current project config as a version baseline.")
    save_parser.add_argument("--project-root", required=True, type=Path)
    save_parser.add_argument("--version", required=True)
    save_parser.add_argument("--baseline-root", type=Path)
    save_parser.add_argument(
        "--dataset-spec",
        action="append",
        help="Override dataset path with name=relative/path. Can be passed multiple times.",
    )

    diff_parser = subparsers.add_parser("diff", help="Compare current project config against a saved version baseline.")
    diff_parser.add_argument("--project-root", required=True, type=Path)
    diff_parser.add_argument("--version", required=True)
    diff_parser.add_argument("--baseline-root", type=Path)
    diff_parser.add_argument("--report-json", type=Path)
    diff_parser.add_argument(
        "--dataset-spec",
        action="append",
        help="Override dataset path with name=relative/path. Can be passed multiple times.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    dataset_specs = resolve_dataset_specs(getattr(args, "dataset_spec", None))

    if args.command == "save-baseline":
        return save_baseline(
            args.project_root.resolve(),
            args.version,
            args.baseline_root.resolve() if args.baseline_root else None,
            dataset_specs,
        )
    if args.command == "diff":
        return diff_baseline(
            args.project_root.resolve(),
            args.version,
            args.baseline_root.resolve() if args.baseline_root else None,
            args.report_json.resolve() if args.report_json else None,
            dataset_specs,
        )
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
