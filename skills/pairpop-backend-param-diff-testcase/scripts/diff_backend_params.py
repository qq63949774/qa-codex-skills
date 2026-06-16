#!/usr/bin/env python3
import argparse
import os
import re
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Set


FILES = [
    "PairPop/Assets/Main/Script/GameSetting.cs",
    "PairPop/Assets/Main/Script/ADConfig.cs",
    "PairPop/Assets/Main/Script/GameConfig.cs",
]


FIELD_RE = re.compile(
    r"^\s*public\s+(?!class\b)(?!static\b)(?:[\w<>\[\], ]+?)\s+(\w+)\s*(?:=|;)",
    re.MULTILINE,
)

TOP_LEVEL_RE = re.compile(r"ContainsKey\(\"([^\"]+)\"\)")


@dataclass
class FileDiff:
    path: str
    added_fields: List[str]
    removed_fields: List[str]
    added_top_level_keys: List[str]


def git_show(repo: str, ref: str, path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return ""


def extract_fields(text: str) -> Set[str]:
    return set(FIELD_RE.findall(text or ""))


def extract_top_level_keys(text: str) -> Set[str]:
    return set(TOP_LEVEL_RE.findall(text or ""))


def grep_usage(repo: str, ref: str, key: str) -> List[str]:
    try:
        out = subprocess.check_output(
            ["git", "grep", "-n", key, ref, "--", "PairPop/Assets/Main", "PairPop/Assets/Script"],
            cwd=repo,
            text=True,
            stderr=subprocess.DEVNULL,
            errors="replace",
        )
    except subprocess.CalledProcessError:
        return []
    lines = [line for line in out.splitlines() if line.strip()]
    focused = []
    for line in lines:
        if (
            f"settingData.{key}" in line
            or f"public int {key}" in line
            or f"public bool {key}" in line
            or f"public float {key}" in line
            or f"public int[] {key}" in line
            or f"public float[] {key}" in line
            or f"public int[][] {key}" in line
            or f"public Dictionary<string, string> {key}" in line
            or f"public Dictionary<string, int> {key}" in line
            or f"public List<" in line and key in line
            or ("DailyTaskSetting" in line and key in {"DailyTask", "rewards", "id", "gap", "items", "itemId", "count"})
            or (key.startswith("inter_") and f"AD.{key}" in line)
        ):
            focused.append(line)
    return focused or lines[:10]


def compare(repo: str, base: str, head: str) -> Dict[str, FileDiff]:
    result: Dict[str, FileDiff] = {}
    for path in FILES:
        old_text = git_show(repo, base, path)
        new_text = git_show(repo, head, path)
        old_fields = extract_fields(old_text)
        new_fields = extract_fields(new_text)
        old_keys = extract_top_level_keys(old_text)
        new_keys = extract_top_level_keys(new_text)
        result[path] = FileDiff(
            path=path,
            added_fields=sorted(new_fields - old_fields),
            removed_fields=sorted(old_fields - new_fields),
            added_top_level_keys=sorted(new_keys - old_keys),
        )
    return result


def render_markdown(repo: str, base: str, head: str, diffs: Dict[str, FileDiff]) -> str:
    lines: List[str] = []
    lines.append(f"# PairPop Backend Parameter Diff")
    lines.append("")
    lines.append(f"- repo: `{repo}`")
    lines.append(f"- base: `{base}`")
    lines.append(f"- head: `{head}`")
    lines.append("")
    lines.append("## Added Fields")
    lines.append("")
    lines.append("| file | field | usage count | first usage |")
    lines.append("|---|---:|---:|---|")
    for diff in diffs.values():
        for field in diff.added_fields:
            usage = grep_usage(repo, head, field)
            first_usage = usage[0].replace("|", "\\|") if usage else "unable to confirm"
            lines.append(f"| `{diff.path}` | `{field}` | {len(usage)} | `{first_usage}` |")
    lines.append("")
    lines.append("## Added Top-Level Setting Keys")
    lines.append("")
    lines.append("| file | key | usage count | first usage |")
    lines.append("|---|---:|---:|---|")
    for diff in diffs.values():
        for key in diff.added_top_level_keys:
            if key in {"rank", "icon", "items"}:
                continue
            usage = grep_usage(repo, head, key)
            first_usage = usage[0].replace("|", "\\|") if usage else "unable to confirm"
            lines.append(f"| `{diff.path}` | `{key}` | {len(usage)} | `{first_usage}` |")
    lines.append("")
    lines.append("## Removed Fields")
    lines.append("")
    lines.append("| file | field |")
    lines.append("|---|---:|")
    any_removed = False
    for diff in diffs.values():
        for field in diff.removed_fields:
            any_removed = True
            lines.append(f"| `{diff.path}` | `{field}` |")
    if not any_removed:
        lines.append("| none | none |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Diff PairPop backend/server setting parameters between git refs.")
    parser.add_argument("--repo", default=os.getcwd(), help="PairPop repository root")
    parser.add_argument("--base", required=True, help="Base git ref")
    parser.add_argument("--head", required=True, help="Head git ref")
    parser.add_argument("--out", help="Write markdown output to path")
    args = parser.parse_args()

    repo = os.path.abspath(args.repo)
    diffs = compare(repo, args.base, args.head)
    markdown = render_markdown(repo, args.base, args.head, diffs)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(markdown)
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
