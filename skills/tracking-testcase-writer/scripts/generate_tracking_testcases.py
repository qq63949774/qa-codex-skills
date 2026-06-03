#!/usr/bin/env python3
"""Generate tracking event QA test cases from an event definition CSV."""

from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable


@dataclass
class PropertyDef:
    name: str
    value_type: str
    description: str
    note1: str


@dataclass
class EventDef:
    module: str
    name: str
    trigger: str
    properties: list[PropertyDef] = field(default_factory=list)


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\u3000", " ")).strip()


def _clean_multiline(value: str | None) -> str:
    if not value:
        return ""
    lines = [re.sub(r"\s+", " ", line).strip() for line in value.splitlines()]
    return "\n".join([line for line in lines if line])


def parse_event_csv(input_path: Path) -> list[EventDef]:
    with input_path.open("r", encoding="utf-8-sig", newline="") as fp:
        rows = list(csv.DictReader(fp))

    events: list[EventDef] = []
    current_module = ""
    current_event: EventDef | None = None

    for row in rows:
        module = _clean(row.get("事件标签"))
        if module:
            current_module = module

        event_name = _clean(row.get("事件名"))
        if event_name:
            current_event = EventDef(
                module=current_module,
                name=event_name,
                trigger=_clean_multiline(row.get("点位触发说明")),
            )
            events.append(current_event)

        if not current_event:
            continue

        prop_name = _clean(row.get("属性名"))
        if not prop_name:
            continue

        current_event.properties.append(
            PropertyDef(
                name=prop_name,
                value_type=_clean(row.get("属性值类型")),
                description=_clean_multiline(row.get("属性说明")),
                note1=_clean_multiline(row.get("备注1")),
            )
        )

    return events


def _strip_list_marker(text: str) -> str:
    return re.sub(r"^\s*\d+\s*[、\.\):：]?\s*", "", text).strip()


def _extract_value_token(text: str) -> tuple[str, str, bool]:
    had_number_prefix = bool(re.match(r"^\s*\d+\s*[、\.\):：]?\s*", text))
    raw = _strip_list_marker(text)
    if not raw:
        return "", "", False

    if "：" in raw or ":" in raw:
        left, right = re.split(r"[:：]", raw, maxsplit=1)
        left = left.strip()
        right = right.strip()
        if right:
            return right, left, True

    match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*$", raw)
    if match:
        token = match.group(1)
        label = raw[: match.start(1)].strip() or token
        return token, label, True

    if had_number_prefix:
        return raw, raw, True

    # Parse compact option lists like "同意、拒绝"
    if "、" in raw and len(raw) <= 30:
        parts = [part.strip() for part in raw.split("、") if part.strip()]
        if 2 <= len(parts) <= 5 and all(len(part) <= 12 for part in parts):
            return raw, raw, True

    return raw, raw, False


def parse_enum_candidates(prop: PropertyDef) -> list[tuple[str, str]]:
    candidates: list[tuple[str, str]] = []
    visited: set[str] = set()

    for source in (prop.note1, prop.description):
        if not source:
            continue
        for line in source.splitlines():
            line = line.strip()
            if not line:
                continue
            value, label, is_structured = _extract_value_token(line)
            if not is_structured:
                continue

            if "、" in value and value == label:
                # Expand compact option lists, e.g. "同意、拒绝".
                parts = [part.strip() for part in value.split("、") if part.strip()]
                for part in parts:
                    key = part.lower()
                    if key in visited:
                        continue
                    visited.add(key)
                    candidates.append((part, part))
                continue

            if not value:
                continue
            key = value.lower()
            if key in visited:
                continue
            visited.add(key)
            candidates.append((value, label))

    if len(candidates) <= 1:
        return []
    return candidates


def _format_property_checklist(properties: Iterable[PropertyDef]) -> str:
    segments = []
    for prop in properties:
        dtype = prop.value_type or "未标注类型"
        segments.append(f"{prop.name}({dtype})")
    return "；".join(segments)


def _format_operation(trigger: str, enum_label: str | None = None) -> str:
    base = _clean(trigger) or "按业务流程触发该事件"
    if enum_label:
        return f"按业务流程执行“{base}”，并构造场景“{enum_label}”。触发后在数数中查询该事件并核对上报。"
    return f"按业务流程执行“{base}”。触发后在数数中查询该事件并核对上报。"


def _test_content(event_name: str, trigger: str, prop_name: str) -> str:
    return f"事件名：{event_name}"


def _scene_hint(event_name: str, trigger: str, prop_name: str | None = None, enum_value: str | None = None) -> str:
    value = (enum_value or "").strip()

    if event_name == "ta_app_start":
        return "冷启动应用并进入首页可交互状态"
    if event_name == "ta_app_install":
        return "卸载后重装应用并首次启动"
    if event_name == "ta_app_end":
        return "进入游戏后切后台并结束进程"

    if event_name == "user_lifecycle_milestone":
        if value:
            return f"新用户按新手引导推进到“{value}”对应节点"
        return "新用户推进任一新手引导节点"

    if event_name == "level_start":
        return "从主界面点击开始进入任意关卡"

    if event_name == "level_lose":
        if prop_name == "lose_reason" and value:
            if value in {"1", "玩家主动重玩"} or "主动重玩" in value:
                return "关卡中打开设置并点击重玩，触发失败结算"
            if value in {"2", "系统判定死局（且未选择使用道具）"} or "死局" in value:
                return "制造死局且不使用道具，触发系统失败结算"
        return "在关卡中触发一次失败结算"

    if event_name == "level_end":
        if prop_name == "end_reason" and value:
            if value in {"1", "正常通关"} or "通关" in value:
                return "完成关卡并进入胜利结算"
            if value in {"2", "用户离开（退出游戏）"} or "离开" in value or "退出" in value:
                return "关卡中途退出到主页"
        return "结束关卡（通关或中途退出）"

    if event_name == "tool_get":
        if prop_name == "tool_source" and value:
            if value == "video_ad":
                return "通过激励广告领取道具"
            if value == "coin":
                return "使用金币购买道具"
        if prop_name == "tool_id" and value:
            return f"获得道具类型“{value}”"
        return "完成一次获得道具行为"

    if event_name == "tool_use":
        if prop_name == "tool_sence" and value:
            if value == "user":
                return "关卡内主动点击道具并使用"
            if value == "pop":
                return "制造死局后在弹窗中点击使用道具"
        if prop_name == "tool_id" and value:
            return f"使用道具类型“{value}”"
        return "关卡内使用一次道具"

    if event_name == "keyButton":
        mapping = {
            "sound_on": "进入设置页并打开音效",
            "sound_off": "进入设置页并关闭音效",
            "vib_on": "进入设置页并打开震动",
            "vib_off": "进入设置页并关闭震动",
            "rate": "进入设置页并点击评价按钮",
        }
        if value in mapping:
            return mapping[value]
        return "进入设置页并执行任一按钮操作"

    if event_name == "page_show":
        mapping = {
            "rate_pop": "触发并展示引导评星浮层",
            "rate_end": "完成引导评星浮层交互并结束",
            "setting_page": "打开设置页面",
        }
        if value in mapping:
            return mapping[value]
        return "打开目标页面并完成展示"

    if event_name == "lunch_permission_get":
        if prop_name == "permission_type" and value:
            return f"首次启动并触发“{value}”权限弹窗"
        if prop_name == "permission_get" and value:
            return f"首次启动权限弹窗中选择“{value}”"
        return "首次启动并处理权限弹窗"

    if event_name == "money_change":
        if prop_name == "change_type" and value:
            if "获得" in value:
                return "完成一次金币获得行为（如通关奖励）"
            if "消耗" in value:
                return "完成一次金币消耗行为（如购买道具）"
        if prop_name == "change_reason" and value:
            if "通关" in value:
                return "通过通关触发金币变动"
            if "购买道具" in value:
                return "通过购买道具触发金币变动"
        return "触发一次金币变动行为"

    if event_name == "move_action_monitor":
        return "通关关卡并触发步数浮层相关流程"

    return _clean(trigger) or "按业务流程触发该事件"


def _short_operation(
    event_name: str,
    trigger: str,
    prop_name: str | None = None,
    enum_value: str | None = None,
) -> str:
    scene = _scene_hint(event_name, trigger, prop_name, enum_value)
    if not prop_name:
        return f"场景：{scene}；查询 event={event_name}。"
    if enum_value is not None:
        return f"场景：{scene}；查询 event={event_name}，核对 {prop_name}={enum_value}。"
    return f"场景：{scene}；查询 event={event_name}，核对属性 {prop_name}。"


def _short_expected(event_name: str, prop: PropertyDef | None = None, enum_value: str | None = None) -> str:
    if not prop:
        return f"event={event_name} 上报成功。"
    dtype = prop.value_type or "未标注类型"
    if enum_value is not None:
        return f"event={event_name} 上报；{prop.name}={enum_value}；类型={dtype}。"
    return f"event={event_name} 上报；{prop.name} 存在；类型={dtype}。"


def build_cases(events: list[EventDef]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for event in events:
        if not event.properties:
            rows.append(
                {
                    "测试内容": f"事件名：{event.name}",
                    "属性名": "",
                    "操作步骤": _clean(event.trigger) or _scene_hint(event.name, event.trigger),
                    "属性值": "",
                    "__事件名": event.name,
                    "__属性名": "",
                    "__属性值": "",
                }
            )
            continue

        for prop in event.properties:
            enum_values = parse_enum_candidates(prop)
            if not enum_values:
                rows.append(
                    {
                        "测试内容": _test_content(event.name, event.trigger, prop.name),
                        "属性名": prop.name,
                        "操作步骤": _clean(event.trigger) or _scene_hint(event.name, event.trigger, prop.name),
                        "属性值": "",
                        "__事件名": event.name,
                        "__属性名": prop.name,
                        "__属性值": "",
                    }
                )
                continue

            for enum_value, enum_label in enum_values:
                rows.append(
                    {
                        "测试内容": _test_content(event.name, event.trigger, prop.name),
                        "属性名": prop.name,
                        "操作步骤": enum_label,
                        "属性值": enum_value,
                        "__事件名": event.name,
                        "__属性名": prop.name,
                        "__属性值": enum_value,
                    }
                )
    return rows


def _iter_code_files(code_root: Path) -> Iterable[Path]:
    allowed_exts = {
        ".swift",
        ".m",
        ".mm",
        ".h",
        ".hpp",
        ".c",
        ".cc",
        ".cpp",
        ".java",
        ".kt",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".lua",
        ".py",
        ".cs",
        ".go",
        ".rs",
        ".json",
        ".plist",
        ".xml",
        ".yaml",
        ".yml",
        ".txt",
    }
    skip_dirs = {
        ".git",
        ".svn",
        ".hg",
        ".idea",
        ".vscode",
        "node_modules",
        "Pods",
        "build",
        "dist",
        "Library",
        "Temp",
        "Logs",
        "Obj",
        "skills",
    }

    for root, dirs, files in os.walk(code_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() not in allowed_exts:
                continue
            yield path


def _normalize_token(token: str) -> str:
    return token.strip().lower()


def _build_token_hits(code_root: Path, tokens: set[str]) -> dict[str, list[str]]:
    token_hits: dict[str, list[str]] = {token: [] for token in tokens if token}
    if not token_hits:
        return token_hits

    max_file_size = 1_500_000
    max_hits_per_token = 4

    for path in _iter_code_files(code_root):
        try:
            if path.stat().st_size > max_file_size:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue

        rel = str(path.relative_to(code_root))
        for token in token_hits:
            if len(token_hits[token]) >= max_hits_per_token:
                continue
            if token in text:
                token_hits[token].append(rel)

    return token_hits


def _merge_hits(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)
    return merged


def _format_paths(paths: list[str]) -> str:
    if not paths:
        return ""
    return "、".join(paths[:2])


def _ai_judge(event_hits: list[str], prop_hits: list[str], value_hits: list[str], has_prop: bool, has_value: bool) -> tuple[str, str, str]:
    confidence = "低"
    reason = "未在代码扫描范围发现事件名关键字。"

    if event_hits:
        confidence = "中"
        reason = f"事件名命中代码文件：{_format_paths(event_hits)}。"

    if has_prop:
        if not prop_hits:
            confidence = "低"
            reason = f"命中事件名，但未命中属性名；事件命中文件：{_format_paths(event_hits)}。"
        else:
            confidence = "中"
            reason = f"事件名与属性名均有命中；参考文件：{_format_paths(_merge_hits(event_hits, prop_hits))}。"
            same = sorted(set(event_hits) & set(prop_hits))
            if same:
                confidence = "高"
                reason = f"事件名与属性名在同一文件命中：{_format_paths(same)}。"

    if has_value:
        if not value_hits:
            confidence = "中"
            reason = f"命中事件名和属性名，但未命中属性值；参考文件：{_format_paths(_merge_hits(event_hits, prop_hits))}。"
        else:
            confidence = "中"
            reason = f"事件名/属性名/属性值均有命中；参考文件：{_format_paths(_merge_hits(event_hits, prop_hits, value_hits))}。"
            same = sorted(set(event_hits) & set(prop_hits) & set(value_hits))
            if same:
                confidence = "高"
                reason = f"事件名/属性名/属性值在同一文件命中：{_format_paths(same)}。"

    result = "通过" if confidence == "高" else "无法判断"
    return result, reason, confidence


def enrich_rows_with_ai(rows: list[dict[str, str]], code_root: Path) -> list[dict[str, str]]:
    tokens: set[str] = set()
    for row in rows:
        for key in ("__事件名", "__属性名", "__属性值"):
            token = _normalize_token(row.get(key, ""))
            if token:
                tokens.add(token)

    token_hits = _build_token_hits(code_root, tokens)

    for row in rows:
        event = _normalize_token(row.get("__事件名", ""))
        prop = _normalize_token(row.get("__属性名", ""))
        value = _normalize_token(row.get("__属性值", ""))

        event_hits = token_hits.get(event, []) if event else []
        prop_hits = token_hits.get(prop, []) if prop else []
        value_hits = token_hits.get(value, []) if value else []

        result, reason, confidence = _ai_judge(
            event_hits=event_hits,
            prop_hits=prop_hits,
            value_hits=value_hits,
            has_prop=bool(prop),
            has_value=bool(value),
        )
        row["测试结果"] = ""
        row["AI测试结果"] = result
        row["ai判定通过原因"] = reason
        row["AI置信度"] = confidence

    return rows


def default_output_path(input_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d")
    return input_path.with_name(f"{input_path.stem}_测试用例_测试版_{stamp}.csv")


def write_cases(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "测试内容",
        "属性名",
        "操作步骤",
        "属性值",
        "测试结果",
        "AI测试结果",
        "ai判定通过原因",
        "AI置信度",
    ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="source event CSV path")
    parser.add_argument("--output", type=Path, help="output testcase CSV path")
    parser.add_argument(
        "--code-root",
        type=Path,
        default=Path.cwd(),
        help="project code root for AI analysis scan (default: current directory)",
    )
    parser.add_argument(
        "--disable-ai-analysis",
        action="store_true",
        help="disable code scan and leave AI columns empty",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    events = parse_event_csv(args.input)
    rows = build_cases(events)
    if args.disable_ai_analysis:
        for row in rows:
            row["测试结果"] = ""
            row["AI测试结果"] = ""
            row["ai判定通过原因"] = ""
            row["AI置信度"] = ""
    else:
        rows = enrich_rows_with_ai(rows, args.code_root.resolve())
    output = args.output or default_output_path(args.input)
    write_cases(output, rows)
    print(f"Parsed events: {len(events)}")
    print(f"Generated cases: {len(rows)}")
    print(f"Output: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
