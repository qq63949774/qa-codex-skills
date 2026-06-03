#!/usr/bin/env python3
"""Read a Feishu/Lark Wiki requirement page and its child requirement docs.

This helper shells out to lark-cli. It is intentionally read-only and writes
only the optional local JSON output file requested by the caller.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from html import unescape
from pathlib import Path
from typing import Any


WIKI_TOKEN_RE = re.compile(r"/wiki/([A-Za-z0-9]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read Feishu Wiki requirement child docs")
    parser.add_argument("--url", required=True, help="Feishu/Lark Wiki URL")
    parser.add_argument("--version", help="Expected requirement version label")
    parser.add_argument("--output", help="Optional JSON output path")
    parser.add_argument(
        "--openclaw-home",
        default=os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")),
        help="OPENCLAW_HOME for lark-cli config",
    )
    parser.add_argument(
        "--switch-user",
        action="store_true",
        help="Temporarily switch lark-cli strict-mode to user, then restore it",
    )
    parser.add_argument(
        "--include-non-docx",
        action="store_true",
        help="Include non-docx child node metadata without fetching body",
    )
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


def require_ok(proc: subprocess.CompletedProcess[str], command: str) -> dict[str, Any]:
    if proc.returncode != 0:
        raise RuntimeError(f"{command} failed\nstdout={proc.stdout}\nstderr={proc.stderr}")
    text = proc.stdout.strip()
    # Some paginated CLI calls print "[page 1] fetching..." before JSON.
    json_start = min([idx for idx in (text.find("{"), text.find("[")) if idx >= 0], default=-1)
    if json_start > 0:
        text = text[json_start:]
    return json.loads(text)


def parse_token(url: str) -> str:
    match = WIKI_TOKEN_RE.search(url)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9]+", url):
        return url
    raise ValueError(f"Cannot parse wiki token from URL: {url}")


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


def strip_content(content: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", content)
    text = re.sub(r"</(p|h1|h2|h3|li|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def fetch_doc(obj_token: str, openclaw_home: str) -> dict[str, Any]:
    proc = run_lark(
        ["docs", "+fetch", "--api-version", "v2", "--doc", obj_token, "--as", "user", "--format", "json"],
        openclaw_home,
    )
    data = require_ok(proc, f"docs +fetch {obj_token}")
    document = data.get("data", {}).get("document", {})
    content = document.get("content", "")
    document["plain_text"] = strip_content(content)
    return document


def main() -> int:
    args = parse_args()
    token = parse_token(args.url)
    original_mode = current_strict_mode(args.openclaw_home)

    if original_mode == "bot" and not args.switch_user:
        raise RuntimeError("strict-mode is bot; rerun with --switch-user after user confirmation")

    if args.switch_user and original_mode != "user":
        set_strict_mode("user", args.openclaw_home)

    try:
        node_proc = run_lark(
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
            args.openclaw_home,
        )
        node_data = require_ok(node_proc, "wiki spaces get_node")
        parent = node_data.get("data", {}).get("node", {})

        list_proc = run_lark(
            [
                "wiki",
                "nodes",
                "list",
                "--params",
                json.dumps(
                    {
                        "space_id": parent.get("space_id"),
                        "parent_node_token": parent.get("node_token"),
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
            args.openclaw_home,
        )
        child_data = require_ok(list_proc, "wiki nodes list")
        items = child_data.get("data", {}).get("items", [])

        children: list[dict[str, Any]] = []
        for item in items:
            title = item.get("title", "")
            obj_type = item.get("obj_type", "")
            child = {"node": item, "skipped": False}
            if obj_type == "docx":
                child["document"] = fetch_doc(item["obj_token"], args.openclaw_home)
            elif args.include_non_docx:
                child["skipped"] = True
                child["skip_reason"] = f"non-docx child node: {obj_type}"
            else:
                continue
            child["is_requirement_candidate"] = obj_type == "docx" and "测试用例" not in title
            children.append(child)

        result = {
            "source_url": args.url,
            "requested_version": args.version,
            "parent_node": parent,
            "child_count": len(children),
            "children": children,
        }

        text = json.dumps(result, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).expanduser().resolve().write_text(text + "\n", encoding="utf-8")
        print(text)
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
