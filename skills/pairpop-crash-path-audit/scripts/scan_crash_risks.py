#!/usr/bin/env python3
"""PairPop 崩溃路径排查辅助脚本。

使用 --testcases 输出中文 QA 崩溃测试用例。
不加 --testcases 时输出静态代码风险线索；线索不等于已确认崩溃。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Iterable


PATTERNS: list[tuple[str, int, re.Pattern[str]]] = [
    ("json-parse", 8, re.compile(r"(JsonConvert\.DeserializeObject|JToken\.Parse|JObject\.Parse|JToken\.Load)")),
    ("numeric-parse", 7, re.compile(r"\b(int|float|double|long)\.Parse\b|Convert\.To(Int|Single|Double)")),
    ("direct-resource-load", 5, re.compile(r"Resources\.Load(All)?<")),
    ("child-lookup", 5, re.compile(r"\.transform\.Find\(")),
    ("component-lookup", 4, re.compile(r"\.GetComponent<[^>]+>\(")),
    ("singleton-chain", 6, re.compile(r"\b(Scene|DataSave|GameSetting|GameBubbleCtr|GameTableCtr|ADBubbleCtr|BubbleHymnCtr)\.Instance\b")),
    ("index-or-key-access", 6, re.compile(r"\[[^\]\n]*(?:i|j|index|Index|count|Count|Length|Random\.Range|\"|\+|-)[^\]\n]*\]")),
    ("random-range", 4, re.compile(r"Random\.Range\(")),
    ("delayed-callback", 6, re.compile(r"(DOVirtual\.DelayedCall|\.OnComplete\(|StartCoroutine\(|Invoke\()")),
    ("ad-or-iap-callback", 7, re.compile(r"(OpenGlobalRewardVideoAd|OpenGlobalInterstitialAd|PurchaseHelper|ProcessPurchase)")),
    ("persistence-network", 6, re.compile(r"(PlayerPrefs|DataSave\.Load|DataSave\.Save|Protocol\.Send|LoadFromServer|SetGameSetting|Client\.GetGameSetting)")),
    ("hard-throw", 9, re.compile(r"\bthrow\b")),
]

IGNORE_DIR_PARTS = {
    ".git",
    "Library",
    "Temp",
    "Obj",
    "Build",
    "Builds",
    "Logs",
    "UserSettings",
}

DEFAULT_OWNED_PREFIXES = (
    "Assets/Script/",
    "Assets/Main/Script/",
    "Assets/Main/Base/",
    "Assets/Main/sdk/",
)

TEST_CASES: list[dict[str, str]] = [
    {
        "case_id": "CRASH-DATA-001",
        "priority": "P0",
        "risk_item": "本地 GameData 损坏后，冷启动可能在进入首页/游戏前崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "使用 Unity Editor 或开发包。将 PlayerPrefs 的 GameData 写成非法 JSON，例如 {bad-json。GameSetting 保持为空或有效，避免混入配置解析问题。",
        "steps": "1. 冷启动 App。\n2. 等待 Loading 流程结束。\n3. 观察是否能进入首页或游戏界面。",
        "expected": "期望不崩溃，并能忽略或修复损坏存档。失败信号：Loading/首页出现前抛出 JsonReaderException 或反序列化异常。",
        "logs": "GameData, DataSave, JsonReaderException, DeserializeObject",
        "evidence": "PairPop/Assets/Main/Script/DataSave.cs:174-186",
        "function": "DataSave.load / DataSave.setGameData / PlayerPrefs GameData",
        "reason": "DataSave.load 读取 GameData 后，setGameData 直接调用 JsonConvert.DeserializeObject<InfoDef>(json)，当前代码未在本函数内 try/catch。",
        "cleanup": "使用 GM 清档，或删除 PlayerPrefs 的 GameData。",
    },
    {
        "case_id": "CRASH-CONFIG-001",
        "priority": "P1",
        "risk_item": "已保存的后台 GameSetting 为非法 JSON 时，冷启动配置加载可能异常。",
        "status": "候选风险；代码看起来有保护，但需要运行时验证",
        "setup": "将 PlayerPrefs 的 GameSetting 写成非法 JSON，例如 {bad-json。GameSettingMd5 可随意写一个非空值。",
        "steps": "1. 冷启动 App。\n2. 观察 DataSave.Awake 阶段控制台日志。\n3. 继续进入首页或第一局游戏。",
        "expected": "期望只打印 SetGameSetting 错误并继续使用默认配置。失败信号：未捕获 JSON 异常、启动中断或无法进入首页/游戏。",
        "logs": "SetGameSetting, JsonReaderException, GameSetting",
        "evidence": "PairPop/Assets/Main/Script/DataSave.cs:281-291",
        "function": "DataSave.SetGameSetting / PlayerPrefs GameSetting",
        "reason": "DataSave.SetGameSetting 对 JObject.Parse 和 GameConfig.SetGameSetting 外层有 try/catch，需要运行确认异常不会外溢。",
        "cleanup": "删除 PlayerPrefs 的 GameSetting 和 GameSettingMd5。",
    },
    {
        "case_id": "CRASH-CONFIG-002",
        "priority": "P1",
        "risk_item": "后台配置缺少 ADSetting/BannerAD/GameSetting 字段时，应使用默认值且不崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "将 PlayerPrefs 的 GameSetting 写成合法但缺字段的 JSON，例如 {} 或 {\"GameSetting\":\"{}\"}。",
        "steps": "1. 冷启动 App。\n2. 进入普通关卡。\n3. 触发一次插屏相关路径，例如开始、重开、退出或胜利。",
        "expected": "期望不崩溃并使用默认配置。失败信号：NullReferenceException、KeyNotFoundException 或配置解析异常。",
        "logs": "ADSetting, BannerAD, GameSetting, NullReferenceException, KeyNotFoundException",
        "evidence": "PairPop/Assets/Main/Script/ADConfig.cs:14-24; PairPop/Assets/Main/Script/GameSetting.cs:16-21",
        "function": "ADConfig.SetGameSetting / GameSetting.SetGameSetting",
        "reason": "ADConfig 和 GameSetting 都有 ContainsKey 判断，但仍需验证后续广告/配置路径是否能正确使用默认值。",
        "cleanup": "删除 PlayerPrefs 的 GameSetting 和 GameSettingMd5。",
    },
    {
        "case_id": "CRASH-LEVEL-001",
        "priority": "P0",
        "risk_item": "本地或云端关卡 JSON 字段异常时，关卡初始化可能崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "使用受控分支或云端测试 payload。逐项尝试：缺少 gridSize、gridSize 写成 3、缺少 data、difficulty 非数字、model=3 缺少 move、model=0/1/2 缺少 time。",
        "steps": "1. 冷启动 App，让 PuzzleDataManager.initPuzzleData 执行。\n2. 进入覆盖该异常数据的关卡。\n3. 观察棋盘首次渲染前是否报错。",
        "expected": "期望拒绝异常关卡并回退或给出非崩溃错误。失败信号：解析阶段出现 NullReferenceException、FormatException、IndexOutOfRangeException。",
        "logs": "PuzzleDataManager, ParseToPuzzleList, FormatException, NullReferenceException, IndexOutOfRangeException",
        "evidence": "PairPop/Assets/Script/Data/PuzzleDataManager.cs:78-85; PairPop/Assets/Script/Data/PuzzleDataManager.cs:164-198",
        "function": "PuzzleDataManager.initPuzzleData / ParseToPuzzleList",
        "reason": "ParseToPuzzleList 直接依赖必要 key 和数字格式，使用 ToString、int.Parse、gridSize.Split('x') 与 data 转换。",
        "cleanup": "恢复原始关卡 JSON，或清理云端关卡更新配置。",
    },
    {
        "case_id": "CRASH-OLD-LEVEL-001",
        "priority": "P1",
        "risk_item": "老用户 currentRoundIndex 超过本地关卡总数，且 LoopStart 异常时可能崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "将 GameData.currentRoundIndex 设置为大于本地 PuzzleData 总数的值。将后台 GameSetting.GameSetting.LoopStart 设置为等于或大于本地关卡总数。",
        "steps": "1. 冷启动 App。\n2. 进入普通关卡。\n3. 观察首个棋盘是否能正常渲染。",
        "expected": "期望自动钳制或回退到有效关卡。失败信号：getLevelData 内出现 DivideByZeroException、取模异常或非法索引。",
        "logs": "PuzzleDataManager, getLevelData, LoopStart, DivideByZeroException, ArgumentOutOfRangeException",
        "evidence": "PairPop/Assets/Script/Data/PuzzleDataManager.cs:274-297; PairPop/Assets/Main/Script/GameSetting.cs:166",
        "function": "PuzzleDataManager.getLevelData / GameSetting.ServerSetting.LoopStart",
        "reason": "当 currentRoundIndex 超过本地关卡数时，loopLength = allLevelDataArrayList.Count - loopStartIndex - 1，并被用于取模计算。",
        "cleanup": "使用 GM 清档，或重置 GameData.currentRoundIndex 和 GameSetting。",
    },
    {
        "case_id": "CRASH-CHALLENGE-001",
        "priority": "P1",
        "risk_item": "GM 强制不存在的挑战关卡时，puzzleData 可能为空并导致挑战启动崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "使用 GM 挑战关卡输入框设置一个极大的关卡 index，确保 ChallengeData 中没有对应 key，然后进入每日挑战。",
        "steps": "1. 使用 GM/开发权限打开 App。\n2. 将挑战关卡 index 设置为很大的值。\n3. 进入每日挑战。\n4. 观察挑战棋盘渲染前是否报错。",
        "expected": "期望回退到有效挑战关或给出非崩溃错误。失败信号：GameCtr.startGame 访问 puzzleData.model 时出现 NullReferenceException。",
        "logs": "challengeKey, getChallengeLevelData, puzzleData, NullReferenceException",
        "evidence": "PairPop/Assets/Script/Data/PuzzleDataManager.cs:300-336; PairPop/Assets/Script/GameCtr.cs:847-864",
        "function": "PuzzleDataManager.getChallengeLevelData / GameCtr.startGame / DataSave.GMChallengeIndex",
        "reason": "forceUseKeyData 为 true 且 key 不存在时会返回 null，GameCtr 后续会访问 puzzleData.model。",
        "cleanup": "重置 DataSave.GMChallengeIndex 或使用 GM 清档。",
    },
    {
        "case_id": "CRASH-MODEL-001",
        "priority": "P1",
        "risk_item": "model=1/3 的 bubble/textBubble 关卡 data 结构异常时，发牌阶段可能崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "使用受控关卡 payload：model 为 1 或 3，data 中包含空 item、非法 card 对象，或缺少 className。",
        "steps": "1. 进入目标 model=1/3 关卡。\n2. 等待棋盘发牌完成。\n3. 如果棋盘已渲染，继续使用 hint/find 道具。",
        "expected": "期望跳过非法 card 或给出可控错误。失败信号：LoadBubble 阶段出现 JSON 解析异常、NullReferenceException 或组件缺失异常。",
        "logs": "GameCtr.dealCardBubbleAction, GameBubbleCtr.LoadBubble, DeserializeObject, NullReferenceException",
        "evidence": "PairPop/Assets/Script/GameCtr.cs:977-1002; PairPop/Assets/Script/GameBubbleCtr.cs:1323-1369",
        "function": "GameCtr.dealCardBubbleAction / GameBubbleCtr.LoadBubble",
        "reason": "model=1/3 会将嵌套 data 展平成 CardJsonData，并为每个 item 实例化 bubble prefab。",
        "cleanup": "恢复关卡数据。",
    },
    {
        "case_id": "CRASH-MODEL-002",
        "priority": "P2",
        "risk_item": "model=2 table 模式的子节点或资源缺失时，accept 状态刷新可能崩溃。",
        "status": "候选风险；需要运行时验证",
        "setup": "进入已知 model=2 的 table 关卡。如排查资源回归，使用 Texture/Table/accept 或 accept1 可能缺失的测试包/分支。",
        "steps": "1. 进入 model=2 关卡。\n2. 执行会刷新 table accept 状态的操作。\n3. 观察 table cell 视觉刷新。",
        "expected": "期望资源缺失时也不崩溃，最多显示兜底 UI。失败信号：accept 子节点或 Image 组件缺失导致 NullReferenceException。",
        "logs": "GameTableCtr, accept, Resources.Load, NullReferenceException",
        "evidence": "PairPop/Assets/Script/GameCtr.cs:1021-1024; PairPop/Assets/Script/GameTableCtr.cs table accept update paths",
        "function": "GameTableCtr accept 刷新 / Resources.Load Texture/Table",
        "reason": "扫描命中 transform.Find(\"accept\").GetComponent<Image>() 和 Resources.Load 后直接赋值的路径。",
        "cleanup": "恢复 table prefab 和相关资源。",
    },
    {
        "case_id": "CRASH-CALLBACK-001",
        "priority": "P1",
        "risk_item": "发牌/引导期间快速重开或退出，延迟回调可能访问已销毁对象。",
        "status": "候选风险；需要运行时验证",
        "setup": "选择有发牌动画或延迟引导/hint 动画的关卡，覆盖 model=1、model=2、model=3。",
        "steps": "1. 开始关卡。\n2. 在发牌或引导动画期间立刻打开设置并重开/退出。\n3. 转场后继续观察日志 3-5 秒。\n4. 分别覆盖不同 model。",
        "expected": "期望旧对象/旧页面关闭后没有异常。失败信号：延迟回调中出现 MissingReferenceException 或 NullReferenceException。",
        "logs": "DOVirtual.DelayedCall, OnComplete, MissingReferenceException, NullReferenceException",
        "evidence": "PairPop/Assets/Script/GameCtr.cs:977-1061; PairPop/Assets/Main/Script/BasePanel.cs close path",
        "function": "GameCtr.dealCardBubbleAction 延迟回调 / BasePanel.close",
        "reason": "DOTween 延迟回调可能在状态变化后继续执行，如果未显式 Kill，可能访问旧对象。",
        "cleanup": "如状态卡住，重启 App。",
    },
    {
        "case_id": "CRASH-AD-001",
        "priority": "P1",
        "risk_item": "激励广告回调返回时页面或游戏状态已变化，可能访问过期对象。",
        "status": "候选风险；需要运行时验证",
        "setup": "使用可跳广告或可控制广告结果的开发包。准备能触发激励广告的入口：复活、获取道具、翻倍奖励、广告气泡。",
        "steps": "1. 打开带激励广告按钮的页面。\n2. 点击激励广告。\n3. 广告等待中或回调刚返回时，尽量执行关闭、重开或转场。\n4. 分别覆盖成功和失败回调。",
        "expected": "期望奖励只发一次或安全忽略，且不崩溃。失败信号：回调访问 Scene.Instance.gameCtr、页面组件或 DataSave.Instance 时出现 NullReference/MissingReference。",
        "logs": "OpenGlobalRewardVideoAd, ADHelper, MissingReferenceException, NullReferenceException",
        "evidence": "PairPop/Assets/Main/Script/ADConfig.cs:97-109",
        "function": "ADConfig.OpenGlobalRewardVideoAd / 页面自定义回调",
        "reason": "激励广告封装会在 SDK 返回后执行调用方传入的回调，但调用方页面可能已关闭。",
        "cleanup": "使用 GM 清档，或重置本次广告带来的道具/金币变化。",
    },
]

def iter_cs_files(root: Path, include_vendor: bool = False) -> Iterable[Path]:
    for path in root.rglob("*.cs"):
        if any(part in IGNORE_DIR_PARTS for part in path.parts):
            continue
        if not include_vendor:
            rel = path.relative_to(root).as_posix()
            if not rel.startswith(DEFAULT_OWNED_PREFIXES):
                continue
        yield path


def strip_comments(line: str) -> str:
    return line.split("//", 1)[0]


def classify_context(path: Path, line: str) -> str:
    text = f"{path.as_posix()} {line}"
    lower = text.lower()
    if "puzzledatamanager" in lower or "puzzledata" in lower or "challengedata" in lower:
        return "level/config"
    if "gamesetting" in lower or "datasave" in lower or "client.getgamesetting" in lower:
        return "server-config/save"
    if "adconfig" in lower or "purchase" in lower or "iap" in lower or "adhelper" in lower:
        return "ad/iap"
    if "gamebubblectr" in lower or "textbubble" in lower or "bubble" in lower:
        return "bubble/text-bubble"
    if "gametablectr" in lower:
        return "table"
    if "basepanel" in lower or "page/" in lower:
        return "page/lifecycle"
    if "language" in lower or "resources.load" in lower:
        return "resource/localization"
    return "general"


def summarize_reason(kinds: list[str]) -> str:
    reason_bits = []
    if "json-parse" in kinds or "numeric-parse" in kinds:
        reason_bits.append("parse may throw on malformed config/data")
    if "index-or-key-access" in kinds or "random-range" in kinds:
        reason_bits.append("key/index/range depends on runtime data")
    if "child-lookup" in kinds or "component-lookup" in kinds or "singleton-chain" in kinds:
        reason_bits.append("object/component/singleton may be null")
    if "delayed-callback" in kinds:
        reason_bits.append("callback may run after state changed")
    if "ad-or-iap-callback" in kinds:
        reason_bits.append("SDK callback may touch stale game/page state")
    if "persistence-network" in kinds:
        reason_bits.append("save/server timing or payload may vary")
    if "direct-resource-load" in kinds:
        reason_bits.append("resource path may be missing")
    if "hard-throw" in kinds:
        reason_bits.append("explicit throw path")
    return "; ".join(reason_bits) or "manual review required"


def scan(root: Path, include_vendor: bool = False) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in iter_cs_files(root, include_vendor=include_vendor):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_no, raw in enumerate(lines, 1):
            line = strip_comments(raw).strip()
            if not line:
                continue
            matched: list[tuple[str, int]] = []
            for kind, weight, pattern in PATTERNS:
                if pattern.search(line):
                    matched.append((kind, weight))
            if not matched:
                continue
            kinds = [kind for kind, _ in matched]
            score = sum(weight for _, weight in matched)
            context = classify_context(path, line)
            if context in {"level/config", "server-config/save", "ad/iap"}:
                score += 3
            elif context in {"bubble/text-bubble", "table", "page/lifecycle"}:
                score += 2
            findings.append(
                {
                    "score": score,
                    "context": context,
                    "kinds": kinds,
                    "path": str(path.relative_to(root)),
                    "line": line_no,
                    "code": raw.strip(),
                    "reason": summarize_reason(kinds),
                }
            )
    findings.sort(key=lambda item: (-int(item["score"]), str(item["path"]), int(item["line"])))
    return findings


def emit_testcases(cases: list[dict[str, str]], as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(cases, ensure_ascii=False, indent=2))
        return

    print(f"测试用例数: {len(cases)}")
    print("说明: 以下为基于当前 PairPop 代码证据整理的可执行崩溃测试用例；只有实际运行后才能标记通过/失败。")
    print()
    for case in cases:
        print(f"{case['case_id']} [{case['priority']}] {case['risk_item']}")
        print(f"状态: {case['status']}")
        print("环境/数据准备:")
        for part in re.split(r"(?<=[。；])\s*", case["setup"]):
            part = part.strip()
            if part:
                print(f"- {part}")
        print("操作步骤:")
        print(case["steps"])
        print(f"预期结果/失败信号: {case['expected']}")
        print(f"日志关键词: {case['logs']}")
        print(f"代码证据: {case['evidence']}")
        print(f"函数/类/配置键: {case['function']}")
        print(f"代码推理: {case['reason']}")
        print(f"清理/重置: {case['cleanup']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描 PairPop C# 崩溃风险，或输出中文 QA 崩溃测试用例。")
    parser.add_argument("project_root", nargs="?", default=".", help="PairPop 仓库根目录")
    parser.add_argument("--top", type=int, default=80, help="输出条数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--include-vendor", action="store_true", help="同时扫描 Packages、Plugins 和第三方 SDK 代码")
    parser.add_argument("--testcases", action="store_true", help="输出中文 QA 崩溃测试用例，而不是原始代码线索")
    args = parser.parse_args()

    root = Path(args.project_root).expanduser().resolve()
    if (root / "PairPop" / "Assets").exists():
        scan_root = root / "PairPop"
    elif (root / "Assets").exists():
        scan_root = root
    else:
        raise SystemExit(f"Could not find Unity Assets folder under {root}")

    if args.testcases:
        emit_testcases(TEST_CASES[: max(0, args.top)], as_json=args.json)
        return 0

    findings = scan(scan_root, include_vendor=args.include_vendor)
    limited = findings[: max(0, args.top)]

    if args.json:
        print(json.dumps(limited, ensure_ascii=False, indent=2))
        return 0

    print(f"scan_root: {scan_root}")
    print(f"total_candidates: {len(findings)}")
    print("contexts:", ", ".join(f"{k}={v}" for k, v in Counter(str(f["context"]) for f in findings).most_common()))
    print()
    for item in limited:
        kinds = ",".join(str(kind) for kind in item["kinds"])
        print(f"[{item['score']:>2}] {item['context']} {item['path']}:{item['line']} {kinds}")
        print(f"     {item['code']}")
        print(f"     lead: {item['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
