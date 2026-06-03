#!/usr/bin/env python3
"""Publish generated testcase CSVs to a Feishu/Lark Wiki child Base.

The script publishes only generated QA artifacts. It never reads or uploads
project source code.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


WIKI_TOKEN_RE = re.compile(r"/wiki/([A-Za-z0-9]+)")
CASE_COLUMNS = ["测试内容", "测试目的", "前置条件", "操作步骤", "期望结果", "需求模块", "测试结果"]
CASE_COLUMNS_WITH_PARAMS = ["测试内容", "测试目的", "前置条件", "新增参数", "操作步骤", "期望结果", "需求模块", "测试结果"]
AI_CASE_COLUMNS = ["AI测试结果", "AI判定原因", "AI测试用例通过率"]
PENDING_COLUMNS = ["测试内容", "待确认点", "风险", "建议确认人", "备注"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish testcase CSVs to Feishu Base")
    parser.add_argument("--wiki-url", required=True, help="Version Wiki URL or token")
    parser.add_argument("--version", required=True, help="Requirement version, e.g. 1.1.0")
    parser.add_argument("--cases", required=True, help="Main testcase CSV path")
    parser.add_argument("--pending", help="Pending testcase CSV path")
    parser.add_argument("--date", help="Output date suffix, e.g. 20260518")
    parser.add_argument("--target-title", default="测试用例", help="Wiki child Base title")
    parser.add_argument("--existing-only", action="store_true", help="Use an existing Wiki child Base only; never create one")
    parser.add_argument("--openclaw-home", default=os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
    parser.add_argument("--switch-user", action="store_true", help="Temporarily switch strict-mode to user")
    return parser.parse_args()


def run_lark(args: list[str], openclaw_home: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["OPENCLAW_HOME"] = openclaw_home
    return subprocess.run(
        ["lark-cli", *args],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def parse_json_stdout(proc: subprocess.CompletedProcess[str], command: str) -> dict[str, Any]:
    if proc.returncode != 0:
        raise RuntimeError(f"{command} failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
    text = proc.stdout.strip()
    json_start = min([idx for idx in (text.find("{"), text.find("[")) if idx >= 0], default=-1)
    if json_start > 0:
        text = text[json_start:]
    data = json.loads(text)
    if isinstance(data, list):
        return {"items": data}
    return data


def parse_token(url: str) -> str:
    match = WIKI_TOKEN_RE.search(url)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9]+", url):
        return url
    raise ValueError(f"Cannot parse wiki token from: {url}")


def current_strict_mode(openclaw_home: str) -> str:
    proc = run_lark(["config", "strict-mode"], openclaw_home)
    if proc.returncode != 0:
        return "unknown"
    match = re.search(r"strict-mode:\s*(\w+)", proc.stdout)
    return match.group(1) if match else "unknown"


def set_strict_mode(mode: str, openclaw_home: str) -> None:
    proc = run_lark(["config", "strict-mode", mode], openclaw_home)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to set strict-mode {mode}: {proc.stdout}\n{proc.stderr}")


def load_csv(path: Path, required_columns: list[str], allow_extra_columns: bool = False) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        if allow_extra_columns:
            valid = fieldnames[: len(required_columns)] == required_columns
            if not valid and required_columns == CASE_COLUMNS:
                valid = fieldnames[: len(CASE_COLUMNS_WITH_PARAMS)] == CASE_COLUMNS_WITH_PARAMS
        else:
            valid = fieldnames == required_columns
        if not valid:
            raise RuntimeError(f"CSV columns mismatch for {path}: {reader.fieldnames}")
        return fieldnames, [{col: row.get(col, "") for col in fieldnames} for row in reader]


def wiki_parent(token: str, openclaw_home: str) -> dict[str, Any]:
    proc = run_lark(
        [
            "wiki",
            "spaces",
            "get_node",
            "--params",
            json.dumps({"token": token, "obj_type": "wiki"}, ensure_ascii=False),
            "--as",
            "user",
            "--format",
            "json",
        ],
        openclaw_home,
    )
    return parse_json_stdout(proc, "wiki spaces get_node").get("data", {}).get("node", {})


def wiki_children(parent: dict[str, Any], openclaw_home: str) -> list[dict[str, Any]]:
    proc = run_lark(
        [
            "wiki",
            "nodes",
            "list",
            "--params",
            json.dumps(
                {
                    "space_id": parent["space_id"],
                    "parent_node_token": parent["node_token"],
                    "page_size": 50,
                },
                ensure_ascii=False,
            ),
            "--as",
            "user",
            "--format",
            "json",
            "--page-all",
        ],
        openclaw_home,
    )
    return parse_json_stdout(proc, "wiki nodes list").get("data", {}).get("items", [])


def create_testcase_base(parent: dict[str, Any], title: str, openclaw_home: str) -> dict[str, Any]:
    proc = run_lark(
        [
            "wiki",
            "+node-create",
            "--space-id",
            parent["space_id"],
            "--parent-node-token",
            parent["node_token"],
            "--obj-type",
            "bitable",
            "--title",
            title,
            "--as",
            "user",
        ],
        openclaw_home,
    )
    data = parse_json_stdout(proc, "wiki +node-create")
    return data.get("data", {}).get("node", data.get("node", data))


def ensure_testcase_base(parent: dict[str, Any], target_title: str, openclaw_home: str, existing_only: bool = False) -> tuple[str, str]:
    children = wiki_children(parent, openclaw_home)
    for child in children:
        if child.get("title") == target_title:
            if child.get("obj_type") == "bitable":
                return child["obj_token"], "existing"
            if existing_only:
                raise RuntimeError(
                    f"Wiki child '{target_title}' exists but obj_type={child.get('obj_type')}; refusing to create a replacement"
                )
            target_title = f"{target_title}-多维表格"
            break
    if existing_only:
        raise RuntimeError(f"Existing Wiki child Base '{target_title}' not found; refusing to create")
    created = create_testcase_base(parent, target_title, openclaw_home)
    return created.get("obj_token") or created.get("token") or created.get("node", {}).get("obj_token"), "created"


def select_options(values: list[str]) -> list[dict[str, str]]:
    palette = ["Blue", "Orange", "Wathet", "Yellow", "Turquoise", "Red", "Purple", "Green", "Carmine"]
    options: list[dict[str, str]] = []
    seen: set[str] = set()
    for value in values:
        name = (value or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        options.append(
            {
                "name": name,
                "hue": palette[(len(options)) % len(palette)],
                "lightness": "Lighter",
            }
        )
    return options


def build_field_defs(columns: list[str], rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    module_options = select_options([row.get("需求模块", "") for row in rows])
    result_options = select_options(["通过", "不通过"])
    fields: list[dict[str, Any]] = []
    for col in columns:
        if col == "需求模块":
            fields.append({"name": col, "type": "select", "multiple": False, "options": module_options})
        elif col in {"测试结果", "AI测试结果"}:
            fields.append({"name": col, "type": "select", "multiple": False, "options": result_options})
        else:
            fields.append({"name": col, "type": "text"})
    return fields


def create_table(base_token: str, table_name: str, columns: list[str], rows: list[dict[str, str]], openclaw_home: str) -> str:
    fields = build_field_defs(columns, rows)
    proc = run_lark(
        [
            "base",
            "+table-create",
            "--base-token",
            base_token,
            "--name",
            table_name,
            "--fields",
            json.dumps(fields, ensure_ascii=False),
            "--as",
            "user",
        ],
        openclaw_home,
    )
    data = parse_json_stdout(proc, "base +table-create")
    table = data.get("data", {}).get("table", data.get("table", data.get("data", {})))
    table_id = table.get("id") or table.get("table_id")
    if not table_id:
        raise RuntimeError(f"Cannot find created table id in response: {data}")
    return table_id


def batch_create_records(base_token: str, table_id: str, rows: list[dict[str, str]], columns: list[str], openclaw_home: str) -> None:
    for start in range(0, len(rows), 400):
        chunk = rows[start : start + 400]
        payload = {"fields": columns, "rows": [[row.get(col, "") for col in columns] for row in chunk]}
        proc = run_lark(
            [
                "base",
                "+record-batch-create",
                "--base-token",
                base_token,
                "--table-id",
                table_id,
                "--json",
                json.dumps(payload, ensure_ascii=False),
                "--as",
                "user",
            ],
            openclaw_home,
        )
        parse_json_stdout(proc, "base +record-batch-create")


def date_suffix(args: argparse.Namespace, cases_path: Path) -> str:
    if args.date:
        return args.date
    match = re.search(r"(20\d{6})", cases_path.name)
    return match.group(1) if match else ""


def main() -> int:
    args = parse_args()
    original_mode = current_strict_mode(args.openclaw_home)
    if original_mode == "bot" and not args.switch_user:
        raise RuntimeError("strict-mode is bot; rerun with --switch-user after user confirmation")
    if args.switch_user and original_mode != "user":
        set_strict_mode("user", args.openclaw_home)

    try:
        cases_path = Path(args.cases).expanduser().resolve()
        pending_path = Path(args.pending).expanduser().resolve() if args.pending else None
        case_columns, cases = load_csv(cases_path, CASE_COLUMNS, allow_extra_columns=True)
        pending_columns, pending = load_csv(pending_path, PENDING_COLUMNS) if pending_path and pending_path.exists() else ([], [])
        parent = wiki_parent(parse_token(args.wiki_url), args.openclaw_home)
        base_token, base_state = ensure_testcase_base(parent, args.target_title, args.openclaw_home, args.existing_only)
        suffix = date_suffix(args, cases_path)

        has_ai_columns = all(col in case_columns for col in AI_CASE_COLUMNS)
        case_table_prefix = f"{args.version}测试用例_AI检查" if has_ai_columns else f"{args.version}测试用例"
        case_table_name = f"{case_table_prefix}_{suffix}" if suffix else case_table_prefix
        case_table_id = create_table(base_token, case_table_name, case_columns, cases, args.openclaw_home)
        batch_create_records(base_token, case_table_id, cases, case_columns, args.openclaw_home)

        result: dict[str, Any] = {
            "base_token": base_token,
            "base_state": base_state,
            "case_table": case_table_name,
            "case_table_id": case_table_id,
            "case_rows": len(cases),
            "case_columns": case_columns,
        }

        if pending:
            pending_table_name = f"{args.version}待确认用例_{suffix}" if suffix else f"{args.version}待确认用例"
            pending_table_id = create_table(base_token, pending_table_name, pending_columns, pending, args.openclaw_home)
            batch_create_records(base_token, pending_table_id, pending, pending_columns, args.openclaw_home)
            result.update(
                {
                    "pending_table": pending_table_name,
                    "pending_table_id": pending_table_id,
                    "pending_rows": len(pending),
                }
            )

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    finally:
        if args.switch_user and original_mode not in {"unknown", "user"}:
            set_strict_mode(original_mode, args.openclaw_home)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
