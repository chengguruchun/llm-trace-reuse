#!/usr/bin/env python3
"""Guard the alias regexes: loosening one silently reroutes real work.

  python3 scripts/test-aliases.py   # exit 1 on drift

Add a case here whenever hit-report.py surfaces a false positive.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import route as RT  # noqa: E402
from quality import (  # noqa: E402
    discard_secret_without_store,
    is_junk,
    is_thin,
    normalize_lesson,
    path_missing_auth_lifecycle,
)

# (query, expected alias or None)
CASES = [
    ("把代码推到远端", "git-push"),
    ("推一下", "git-push"),
    ("git push origin main", "git-push"),
    ("跑一下核心回归测试", "run-tests"),
    ("run the tests", "run-tests"),
    ("跑一下检索", "retrieve"),
    ("找相似的历史路径", "retrieve"),
    ("蒸馏一下", "distill"),
    ("效率评估", "eval-loo"),
    # Describing a topic is not an imperative to run it.
    ("分析一下本地记忆效果然后是否可以开源", None),
    ("修检索漏数据和明文口令", None),
    ("pytest 的超时怎么配", None),
    ("文档里写了 git push 的流程", None),
]

JUNK = [
    {"task": "用户确认修复实测结果（ok）", "preferred_path": ["等用户确认"]},
    {"task": "系统通知：检查完成", "preferred_path": ["无"]},
    {"task": "随便问问（短问）", "preferred_path": ["答疑"]},
]
NOT_JUNK = [
    {"task": "确认分页最后除法向下取整", "preferred_path": ["改 Math.Floor"]},
    {"task": "跑核心回归测试", "preferred_path": ["python3 -m pytest tests/"]},
]

PREF_CASES = [
    ("打开浏览器看下页面", "Browser"),
    ("截图发我", "Browser"),
    ("跑一下核心回归测试", "Tests"),
    ("看下日志为什么失败", "Logs"),
    ("把代码推到远端", "Git push"),
    ("给你 token 推一下", "Git push"),
    ("蒸馏失败模式", "Distill"),
]


def main() -> int:
    fails = []
    for query, domain in PREF_CASES:
        got = [p["domain"] for p in RT.preferences(query)]
        if domain and domain not in got:
            fails.append(f"prefs {query!r}: expected {domain}, got {got}")
        if not domain and got:
            fails.append(f"prefs {query!r}: expected none, got {got}")
    prefs = RT.preferences("打开浏览器")
    if not prefs or not prefs[0]["prefs"]:
        fails.append("preferences.md parsed but prefs list empty — 格式坏了")
    for query in ("打开浏览器验证下页面", "跑一下核心回归", "看下报错日志"):
        got = [p["domain"] for p in RT.preferences(query)]
        if len(got) > 1:
            fails.append(f"prefs {query!r}: 触发词重叠，注入了 {got}")

    for query, expected in CASES:
        got = next((n for p, n in RT.ALIASES if p.search(query)), None)
        if got != expected:
            fails.append(f"alias {query!r}: expected {expected}, got {got}")

    for ep in JUNK:
        if not is_junk(ep):
            fails.append(f"junk not detected: {ep['task']!r}")
    for ep in NOT_JUNK:
        if is_junk(ep):
            fails.append(f"false junk: {ep['task']!r}")
    if is_thin({"task": "x", "preferred_path": ["跑 python3 -m pytest"], "outcome": {"ok": True}}):
        fails.append("concrete step should not count as thin")

    bad_lesson = "token_in_chat 密钥进对话 只收 PAT，askpass 用完即弃，轨迹写 <PAT>"
    if not discard_secret_without_store(bad_lesson):
        fails.append("discard_secret_without_store should flag 用完即弃")
    fixed = normalize_lesson(bad_lesson)
    if "【纠偏】" not in fixed or ".pathbook/secrets" not in fixed:
        fails.append(f"normalize_lesson should append store-reuse: {fixed!r}")
    ok_lesson = "写入 .pathbook/secrets 覆盖复用；失败再问 token"
    if discard_secret_without_store(ok_lesson):
        fails.append("local-store advice must not be treated as discard-only")
    if path_missing_auth_lifecycle(["GIT_ASKPASS one-shot", "git push origin"]):
        pass
    else:
        fails.append("ASKPASS+push without save should be auth lifecycle gap")
    if path_missing_auth_lifecycle(
        ["失败问 token", "save .pathbook/secrets", "push 读本地"]
    ):
        fails.append("full auth lifecycle path should not be a gap")

    # Open-source phrasing must not steal the git-push alias.
    oss = "可以的，需要在个人 github 上开源，新起个项目，业务代码不能推送"
    if next((n for p, n in RT.ALIASES if p.search(oss)), None) == "git-push":
        fails.append("open-source request must not alias to git-push")

    for f in fails:
        print("FAIL " + f, file=sys.stderr)
    extra = 6
    total = len(CASES) + len(PREF_CASES) + len(JUNK) + len(NOT_JUNK) + extra
    print(f"{total} checks, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
