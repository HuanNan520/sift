#!/usr/bin/env python3
"""Sift vault recheck agent: AI-driven kill / merge / rewrite suggestions.

Scans cards in batches, asks an LLM to verdict each (keep/kill/merge/rewrite),
soft-deletes kills to _trash/, writes a markdown week report, notifies Telegram.

Usage:
    recheck-agent.py [--dry-run] [--week YYYY-Www] [--category research|debug|scripts|decisions]

Note: this is sift-agent (LLM-driven). The simpler `recheck.py` is the
expires-based rule check; this one uses an LLM to judge content quality.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import date, datetime
from pathlib import Path


def _envpath(name: str, default: Path) -> Path:
    v = os.environ.get(name, "")
    return Path(v) if v else default


VAULT = _envpath("SIFT_ROOT", Path.home() / "claude-journal")
VAULT_SKILLS = VAULT / "skills"
TRASH = _envpath("SIFT_TRASH", VAULT_SKILLS / "_trash")
REPORTS = _envpath("SIFT_REPORTS", VAULT / "sift" / "_reports")
LOG_PATH = _envpath("SIFT_LOG_DIR", Path.home() / ".claude" / "hooks") / "recheck-agent.log"
SF_KEY_PATH = _envpath(
    "SIFT_SF_KEY_MEMORY",
    Path.home() / ".claude/projects/-home-huannan/memory/reference_siliconflow_api.md",
)

SF_URL = os.environ.get("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
SF_MODEL = os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8000"))

CATEGORIES = ["research", "debug", "decisions", "scripts"]
BATCH_SIZE = 8
BODY_PREVIEW_CHARS = 800

VERDICT_VALUES = {"keep", "kill", "merge", "rewrite"}


def log(msg: str):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [recheck] {msg}\n")
    except Exception:
        pass


def load_sf_key() -> str:
    for var in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
        v = os.environ.get(var, "")
        if v.startswith("sk-"):
            return v
    if not SF_KEY_PATH.exists():
        return ""
    try:
        content = SF_KEY_PATH.read_text(encoding="utf-8")
        m = re.search(r"\*\*Key\*\*:\s*`(sk-[^`]+)`", content)
        return m.group(1) if m else ""
    except Exception:
        return ""


def parse_frontmatter(content: str):
    m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if not m:
        return None, content
    fm_text = m.group(1)
    body = content[m.end():]
    fm = {}
    current_list_key = None
    for line in fm_text.split("\n"):
        if not line.strip():
            current_list_key = None
            continue
        if line.startswith("  - "):
            if current_list_key:
                v = line[4:].strip().strip("'\"")
                fm[current_list_key].append(v)
            continue
        m2 = re.match(r'^(\S+):\s*(.*)$', line)
        if m2:
            k, v = m2.group(1), m2.group(2)
            if v == "":
                fm[k] = []
                current_list_key = k
            else:
                v = v.strip().strip("'\"")
                if v.lower() == "true":
                    v = True
                elif v.lower() == "false":
                    v = False
                fm[k] = v
                current_list_key = None
    return fm, body


def load_cards(categories: list) -> list:
    cards = []
    for cat in categories:
        cat_dir = VAULT_SKILLS / cat
        if not cat_dir.exists():
            continue
        for path in sorted(cat_dir.glob("*.md")):
            try:
                content = path.read_text(encoding="utf-8")
            except Exception:
                continue
            fm, body = parse_frontmatter(content)
            if fm is None:
                continue
            cards.append({
                "path": str(path),
                "rel_path": str(path.relative_to(VAULT)),
                "category": cat,
                "type": fm.get("type", cat),
                "date": str(fm.get("date", "")),
                "tags": fm.get("tags") or [],
                "expires": str(fm.get("expires") or ""),
                "problem": str(fm.get("problem") or fm.get("context") or fm.get("purpose") or "")[:300],
                "solution_summary": str(fm.get("solution-summary") or fm.get("choice") or "")[:300],
                "body_preview": (body[:BODY_PREVIEW_CHARS]).strip(),
            })
    return cards


SYSTEM_PROMPT = """你是 sift vault 的复盘 agent。一次给你 8 张以下卡片的元数据 + 正文摘要,判断每张:keep / kill / merge / rewrite。

判断规则:

**keep** — 卡片仍有复用价值,不动:
- 有具体技术细节(命令 / 代码 / 错误信息)
- 跟当前栈仍相关
- 决策依据没失效

**kill** — 卡片该砍(soft delete 到 _trash):
- 单次问题答案,只用过一次,没未来复用价值
- 针对过时模型/工具/版本(Opus 4.6 调优、上代 SD 节点图等)
- 内容空洞 / 只是闲聊存档
- 跟近期更全面的卡内容重复

**merge** — 跟其他卡内容重复或互补(只在报告里标记,不自动执行):
- 题目相似,内容部分重叠
- 几张同主题应该统一

**rewrite** — 内容还有价值但写得不行(只在报告里标记):
- 信息散乱、缺关键细节、章节缺失
- 应该重写但当前内容还能保留

谨慎用 kill — 默认倾向 keep,只有明确无价值才 kill。

输出格式:{"verdicts": [{"path": "skills/.../xxx.md", "verdict": "keep|kill|merge|rewrite", "reason": "一句中文,具体到点"}]}

path 必须用我传入的 rel_path 完整字符串,不要截短。
"""


def call_llm(messages: list, timeout: int = 120):
    key = load_sf_key()
    if not key:
        log("call_llm: no SF key")
        return None
    body = json.dumps({
        "model": SF_MODEL,
        "messages": messages,
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        SF_URL, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            text = payload["choices"][0]["message"]["content"].strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            return json.loads(text)
        except json.JSONDecodeError as e:
            log(f"call_llm: bad JSON (attempt {attempt}): {e}")
            if attempt == 2:
                return None
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as e:
            log(f"call_llm: api fail (attempt {attempt}): {e}")
            if attempt == 2:
                return None
    return None


def batch_judge(cards: list) -> list:
    parts = ["下面是 8 张以下卡片,逐张判定 keep/kill/merge/rewrite,输出 JSON。\n"]
    for c in cards:
        parts.append(
            f"--- {c['rel_path']} ---\n"
            f"类型: {c['type']}\n"
            f"日期: {c['date']}\n"
            f"过期: {c['expires'] or 'n/a'}\n"
            f"tags: {c['tags']}\n"
            f"问题/context/purpose: {c['problem']}\n"
            f"摘要/choice: {c['solution_summary']}\n"
            f"正文前 {BODY_PREVIEW_CHARS} 字:\n{c['body_preview']}\n"
        )
    user_msg = "\n".join(parts)

    result = call_llm([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ])
    if result is None:
        return []
    verdicts = result.get("verdicts") if isinstance(result, dict) else result
    if not isinstance(verdicts, list):
        log(f"batch_judge: unexpected output type {type(verdicts)}")
        return []
    return [v for v in verdicts if isinstance(v, dict) and v.get("verdict") in VERDICT_VALUES]


def execute_kill(card_path: Path, week_iso: str, dry_run: bool):
    target_dir = TRASH / week_iso
    target = target_dir / card_path.name
    if dry_run:
        return target
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        i = 2
        while target.exists():
            target = target_dir / f"{card_path.stem}-{i}{card_path.suffix}"
            i += 1
        card_path.rename(target)
        return target
    except Exception as e:
        log(f"execute_kill fail {card_path}: {e}")
        return None


def write_report(week_iso: str, actions: list, dry_run: bool):
    REPORTS.mkdir(parents=True, exist_ok=True)
    by_verdict = {"keep": [], "kill": [], "merge": [], "rewrite": []}
    for a in actions:
        by_verdict.setdefault(a["verdict"], []).append(a)

    lines = [
        f"# Sift 复盘周报 · {week_iso}",
        "",
        f"扫描时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"扫描卡片: {sum(len(v) for v in by_verdict.values())} 张",
        f"模式: {'dry-run(未动文件)' if dry_run else '已执行 kill(soft delete)'}",
        "",
        "## 分类统计",
        "",
        f"- 🟢 keep: {len(by_verdict['keep'])} 张",
        f"- 🔴 kill: {len(by_verdict['kill'])} 张" + (" (未执行)" if dry_run else ""),
        f"- 🟡 merge: {len(by_verdict['merge'])} 张 (仅标记,人工跑)",
        f"- 🟣 rewrite: {len(by_verdict['rewrite'])} 张 (仅标记,人工跑)",
        "",
    ]

    if by_verdict["kill"]:
        lines.append("## 🔴 已 soft delete(kill)")
        lines.append("")
        lines.append(f"回收站: `skills/_trash/{week_iso}/`,30 天内可 mv 回 `skills/` 反悔。")
        lines.append("")
        for a in by_verdict["kill"]:
            lines.append(f"- `{a['path']}`")
            lines.append(f"  - reason: {a['reason']}")
        lines.append("")

    if by_verdict["merge"]:
        lines.append("## 🟡 建议合并(merge,人工跑)")
        lines.append("")
        for a in by_verdict["merge"]:
            lines.append(f"- `{a['path']}`")
            lines.append(f"  - reason: {a['reason']}")
        lines.append("")

    if by_verdict["rewrite"]:
        lines.append("## 🟣 建议重写(rewrite,人工跑)")
        lines.append("")
        for a in by_verdict["rewrite"]:
            lines.append(f"- `{a['path']}`")
            lines.append(f"  - reason: {a['reason']}")
        lines.append("")

    if by_verdict["keep"]:
        lines.append("## 🟢 保留(keep)")
        lines.append("")
        lines.append(f"<details><summary>{len(by_verdict['keep'])} 张</summary>\n")
        for a in by_verdict["keep"]:
            lines.append(f"- `{a['path']}` — {a['reason']}")
        lines.append("\n</details>")
        lines.append("")

    content = "\n".join(lines)
    suffix = ".dry-run.md" if dry_run else ".md"
    target = REPORTS / f"{week_iso}{suffix}"
    try:
        target.write_text(content, encoding="utf-8")
        return target
    except Exception as e:
        log(f"write_report fail: {e}")
        return None


def send_tg(text: str):
    token = os.environ.get("TG_BOT_TOKEN", "")
    chat_id = os.environ.get("TG_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        body = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"}, method="POST"
        ), timeout=10)
    except Exception as e:
        log(f"send_tg fail: {e}")


def main():
    p = argparse.ArgumentParser(
        description="Sift vault recheck agent (LLM-driven). Default is dry-run; "
                    "review the report and pass --execute to actually soft-delete.")
    p.add_argument("--execute", action="store_true",
                   help="Actually perform soft-delete (default is dry-run).")
    p.add_argument("--dry-run", action="store_true",
                   help="(default behavior; kept for clarity / back-compat)")
    p.add_argument("--week", help="ISO week (default current, e.g. 2026-W19)")
    p.add_argument("--category", choices=CATEGORIES, help="Single category only")
    args = p.parse_args()
    # default to dry-run unless --execute is passed
    args.dry_run = not args.execute

    today = date.today()
    week_iso = args.week or f"{today.year}-W{today.isocalendar().week:02d}"
    cats = [args.category] if args.category else CATEGORIES

    log(f"start: week={week_iso}, dry_run={args.dry_run}, cats={cats}")
    print(f"Sift recheck-agent · week={week_iso} · dry-run={args.dry_run} · cats={cats}", file=sys.stderr)

    cards = load_cards(cats)
    print(f"loaded {len(cards)} cards", file=sys.stderr)

    if not cards:
        print("no cards to scan", file=sys.stderr)
        return 0

    actions = []
    total_batches = (len(cards) + BATCH_SIZE - 1) // BATCH_SIZE
    for i in range(0, len(cards), BATCH_SIZE):
        batch = cards[i:i + BATCH_SIZE]
        bi = i // BATCH_SIZE + 1
        print(f"batch {bi}/{total_batches}: {len(batch)} cards", file=sys.stderr)
        verdicts = batch_judge(batch)
        if not verdicts:
            log(f"batch {bi}: no verdicts (LLM fail or empty),fallback all keep")
            for c in batch:
                actions.append({"path": c["rel_path"], "verdict": "keep", "reason": "LLM 调用失败/超时,默认保留"})
            continue
        # Build path lookup for fallback
        batch_paths = {c["rel_path"] for c in batch}
        seen_paths = set()
        for v in verdicts:
            v_path = v.get("path", "")
            seen_paths.add(v_path)
            actions.append({
                "path": v_path,
                "verdict": v["verdict"],
                "reason": v.get("reason", ""),
            })
        # any card LLM forgot to verdict → keep
        for c in batch:
            if c["rel_path"] not in seen_paths:
                actions.append({"path": c["rel_path"], "verdict": "keep", "reason": "LLM 未返回 verdict,默认保留"})

    killed = []
    for a in actions:
        if a["verdict"] == "kill":
            abs_path = VAULT / a["path"]
            if abs_path.exists():
                trash_target = execute_kill(abs_path, week_iso, args.dry_run)
                if trash_target:
                    killed.append((a["path"], str(trash_target)))

    report_path = write_report(week_iso, actions, args.dry_run)

    summary = (
        f"📊 *sift recheck* week `{week_iso}`"
        + (" (dry-run)" if args.dry_run else "") + "\n"
        f"scanned: {len(actions)} · "
        f"kill: {sum(1 for a in actions if a['verdict'] == 'kill')} · "
        f"merge: {sum(1 for a in actions if a['verdict'] == 'merge')} · "
        f"rewrite: {sum(1 for a in actions if a['verdict'] == 'rewrite')} · "
        f"keep: {sum(1 for a in actions if a['verdict'] == 'keep')}\n"
        f"report: `{report_path}`"
    )
    print(summary, file=sys.stderr)
    send_tg(summary)
    log(f"done: kills={len(killed)} report={report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
