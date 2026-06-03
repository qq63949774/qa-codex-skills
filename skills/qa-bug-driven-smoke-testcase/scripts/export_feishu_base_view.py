#!/usr/bin/env python3
"""Export a Feishu/Lark Base table view to CSV.

Reads records only. Intended for QA Bug List intake before risk-clustered
release-check testcase generation.
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
from urllib.parse import parse_qs, urlparse


WIKI_TOKEN_RE = re.compile(r"/wiki/([A-Za-z0-9]+)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Feishu Base view records to CSV")
    parser.add_argument("--url", help="Feishu Wiki/Base URL. Query may contain table= and view=")
    parser.add_argument("--base-token", help="Base app token, if already known")
    parser.add_argument("--table-id", help="Table id/name. Overrides URL table query")
    parser.add_argument("--view-id", help="View id/name. Overrides URL view query")
    parser.add_argument("--output", default="feishu_buglist_rc.csv", help="Output CSV path")
    parser.add_argument("--openclaw-home", default=os.environ.get("OPENCLAW_HOME", str(Path.home() / ".openclaw")))
    parser.add_argument("--limit", type=int, default=200)
    return parser.parse_args()


def run_lark(args: list[str], openclaw_home: str) -> dict:
    env = os.environ.copy()
    env["OPENCLAW_HOME"] = openclaw_home
    proc = subprocess.run(
        ["lark-cli", *args],
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        print(proc.stdout, file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)

    text = proc.stdout.strip()
    json_start = min([idx for idx in (text.find("{"), text.find("[")) if idx >= 0], default=-1)
    if json_start > 0:
        text = text[json_start:]
    return json.loads(text)


def parse_url(url: str | None) -> tuple[str | None, str | None, str | None]:
    if not url:
        return None, None, None
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    table_id = (query.get("table") or [None])[0]
    view_id = (query.get("view") or [None])[0]
    match = WIKI_TOKEN_RE.search(url)
    wiki_token = match.group(1) if match else None
    return wiki_token, table_id, view_id


def wiki_to_base_token(wiki_token: str, openclaw_home: str) -> str:
    data = run_lark(
        [
            "wiki",
            "spaces",
            "get_node",
            "--params",
            json.dumps({"token": wiki_token, "obj_type": "wiki"}, ensure_ascii=False),
            "--as",
            "user",
            "--format",
            "json",
        ],
        openclaw_home,
    )
    node = data.get("data", {}).get("node", {})
    if node.get("obj_type") != "bitable":
        raise SystemExit(f"Wiki node is not a Base/bitable: obj_type={node.get('obj_type')}")
    token = node.get("obj_token")
    if not token:
        raise SystemExit("Unable to resolve Base token from Wiki node")
    return token


def normalize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                if item.get("name") is not None:
                    parts.append(str(item["name"]))
                elif item.get("text") is not None:
                    parts.append(str(item["text"]))
                elif item.get("file_token") is not None:
                    parts.append(str(item.get("name") or item["file_token"]))
                else:
                    parts.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
            else:
                parts.append(str(item))
        return ";".join(parts)
    if isinstance(value, dict):
        if value.get("name") is not None:
            return str(value["name"])
        if value.get("text") is not None:
            return str(value["text"])
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def main() -> int:
    args = parse_args()
    wiki_token, url_table_id, url_view_id = parse_url(args.url)
    base_token = args.base_token or (wiki_to_base_token(wiki_token, args.openclaw_home) if wiki_token else None)
    table_id = args.table_id or url_table_id
    view_id = args.view_id or url_view_id

    if not base_token or not table_id:
        raise SystemExit("Need --url containing a Base Wiki node and table query, or --base-token plus --table-id")

    rows: list[dict[str, str]] = []
    fields: list[str] | None = None
    offset = 0
    limit = max(1, min(args.limit, 200))

    while True:
        cmd = [
            "base",
            "+record-list",
            "--base-token",
            base_token,
            "--table-id",
            table_id,
            "--limit",
            str(limit),
            "--offset",
            str(offset),
            "--format",
            "json",
        ]
        if view_id:
            cmd.extend(["--view-id", view_id])

        data = run_lark(cmd, args.openclaw_home)
        payload = data.get("data", {})
        batch = payload.get("data", [])
        record_ids = payload.get("record_id_list", [])
        if fields is None:
            fields = payload.get("fields", [])

        for record_id, values in zip(record_ids, batch):
            row = {"record_id": record_id}
            for name, value in zip(fields, values):
                row[name] = normalize(value)
            rows.append(row)

        if not payload.get("has_more") or not batch:
            break
        offset += len(batch)

    output = Path(args.output).expanduser().resolve()
    columns = ["record_id"] + list(fields or [])
    with output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"rows": len(rows), "output": str(output), "base_token": base_token, "table_id": table_id, "view_id": view_id}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
