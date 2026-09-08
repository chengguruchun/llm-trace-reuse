#!/usr/bin/env python3
"""critique.mode 的受控词表 + 归类器。

为什么需要这层：distill.py 按 mode 精确字符串计数，count>=2 才提示"蒸馏成
playbook"。但历史上 mode 被写成一次性的具体描述，这种粒度不可能出现第二次，
蒸馏因此空转。

做法是不改历史数据：mode 原文保留，另外把它归到十几个**槽位**上，按槽位计数。

新写 episode 时 mode 请直接用槽位名，细节写进 better / fix。
"""
from __future__ import annotations

import re

# 槽位 -> (中文说明, 匹配关键词)。顺序即优先级，先匹配到的胜出。
SLOTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("trace_hygiene", "轨迹记录本身没做好（漏记、记了不复用、字段没人读）", (
        "pathbook", "forgot_", "log_without_reuse", "junk_episode",
        "optional_logging", "lesson_content_lost", "unread_field",
        "quarantine", "stale_reuse", "rule_not_executed", "hidden_cot",
        "bad_case", "轨迹", "复盘",
    )),
    ("metric_misuse", "指标读错、用自己的改动自证、或数字过期", (
        "metric", "inflated", "stale_numbers", "unmeasured", "指标", "数字",
    )),
    ("premature_claim", "没验证就宣称完成 / 根因判断错 / 首轮就交差", (
        "premature", "cited_note", "ship_without", "wrong_root_cause",
        "wrong_icon", "first_pass", "没验证", "宣称",
    )),
    ("false_positive", "检查或规则误报（正则太宽、把 A 的信号当 B）", (
        "false_positive", "regex", "treated_", "误报",
    )),
    ("wrong_scope", "作用域/范围判断错：漏查入口、看错产物、等待收得太早", (
        "without_checking", "wrong_artifact", "too_early", "scope", "作用域", "范围",
    )),
    ("secret_hygiene", "密钥进 URL/对话明文；≠禁止本机 .pathbook/secrets 覆盖复用", (
        "token_in_chat", "secret", "gated_knowledge", "密钥", "令牌", "用完即弃",
    )),
    ("stale_creds", "凭证过期：失败即问用户；本机存覆盖；下次复用（生命周期）", (
        "creds", "stale_local", "login", "凭证", "登录",
    )),
    ("env_setup", "环境装配问题：SDK 钉版本、行尾、库名猜错", (
        "sdk", "global_json", "env-", "env_", "crlf", "db-name", "db_name",
        "环境", "行尾",
    )),
    ("platform_limit", "平台/系统/浏览器的硬限制，不是代码能绕的", (
        "mac_blocks", "cannot_suppress", "cannot_replace", "promised_checkbox",
        "not_in_docker", "browser", "protocol_prompt", "限制",
    )),
    ("doc_inconsistent", "文档或注释自相矛盾 / 与实际不符", (
        "docs_said", "reg_comment", "文档", "注释",
    )),
    ("code_smell", "实现层面的坏味道：重复、硬编码、漏 using、宽 catch", (
        "duplicated", "missing_using", "hardcode", "broad_catch",
        "weak_persist", "重复", "硬编码",
    )),
    ("tool_eval", "三方工具/依赖选型评估", (
        "third-party", "third_party", "tool-eval", "tool_eval", "选型",
    )),
]

SLOT_NAMES = tuple(name for name, _, _ in SLOTS)
SLOT_DESC = {name: desc for name, desc, _ in SLOTS}

UNCLASSIFIED = "unclassified"


def slot_of(mode: str) -> str:
    """把任意写法的 mode 归到槽位；归不上返回 unclassified。"""
    s = (mode or "").strip().lower()
    if not s:
        return UNCLASSIFIED
    if s in SLOT_NAMES:
        return s
    for name, _, keys in SLOTS:
        for k in keys:
            if k in s:
                return name
    return UNCLASSIFIED


def looks_like_prose(mode: str) -> bool:
    """散文式 mode：既无法精确重复，也占满了本该给 better/fix 的位置。"""
    s = (mode or "").strip()
    return len(s) > 40 or bool(re.search(r"[，。；、！？]", s))


if __name__ == "__main__":
    for name, desc, _ in SLOTS:
        print(f"{name:18s} {desc}")
