#!/usr/bin/env python3
"""
sift care-agent v1 · 主动关心代理

核心机制(Claude Bypass 同构):
  AI 完成一次决策 → 自己决定下次几分钟后再醒
  系统按时唤醒 → 喂上下文 → 决策 → 自循环

数据感知 v1(简化):
  - vault 最近活动(7 天内新写/修改的卡)
  - 当前时间(小时 / 周几)
  - 上次决策的 audit log
  - 上次预期的 next_context

执行动作 v1:
  - push_telegram(给用户推消息)
  - 后期:调米家 / 调日历 / 调外卖 API

透明性:每次决策进 audit 表 · 用户随时翻。
"""
import os
import re
import sys
import json
import time
import sqlite3
import argparse
import requests
import frontmatter
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ────────── env ──────────

LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or ""
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

# v1 SaaS · per-user vault under SIFT_USERS_ROOT/{uid}/vault
SIFT_USERS_ROOT = Path(os.environ.get("SIFT_USERS_ROOT", "/vol1/1000/sift/users"))
DB_PATH = Path(os.environ.get("SIFT_DB", "/vol1/1000/sift/sift.sqlite"))
LOG_DIR = Path(os.environ.get("SIFT_LOG_DIR", "/vol1/1000/sift/logs"))
LOG_DIR.mkdir(exist_ok=True, parents=True)


def get_user_vault(uid: int) -> Path:
    return SIFT_USERS_ROOT / str(int(uid)) / "vault"


# Default user (alpha) — overridden by care_schedule rows per user.
DEFAULT_USER_ID = 1
TZ = timezone(timedelta(hours=8))  # 中国时区


# ────────── db ──────────

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS care_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            trigger_at INTEGER NOT NULL,
            context TEXT,
            state TEXT DEFAULT 'pending',
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_schedule_due ON care_schedule(state, trigger_at);

        CREATE TABLE IF NOT EXISTS care_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            fired_at INTEGER NOT NULL,
            data_snapshot TEXT,
            reasoning TEXT,
            should_engage INTEGER,
            message TEXT,
            actions TEXT,
            next_trigger_at INTEGER,
            next_context TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_user ON care_audit(user_id, fired_at DESC);
    """)
    conn.commit()
    conn.close()


# ────────── 数据收集 ──────────

def collect_vault_activity(uid: int, days: int = 7, max_cards: int = 20) -> str:
    """收集指定用户 vault 最近活动 · 给 LLM 看"""
    vault_root = get_user_vault(uid)
    if not vault_root.exists():
        return "(vault 不存在)"

    cutoff = time.time() - days * 86400
    recent = []
    for p in vault_root.rglob("*.md"):
        try:
            mtime = p.stat().st_mtime
            if mtime < cutoff:
                continue
            size = p.stat().st_size
            if size < 50:  # 跳过太短的
                continue
            recent.append((mtime, p, size))
        except FileNotFoundError:
            continue

    recent.sort(reverse=True)
    recent = recent[:max_cards]

    if not recent:
        return f"(过去 {days} 天 vault 没动 · 用户可能不活跃 · 或没在用 sift)"

    lines = [f"# 过去 {days} 天 vault 活动({len(recent)} 张卡)"]
    for mtime, p, size in recent:
        dt = datetime.fromtimestamp(mtime, TZ).strftime("%m-%d %H:%M")
        # 拿 frontmatter 的 title / tags
        try:
            post = frontmatter.load(p)
            title = post.metadata.get("title", p.stem)
            tags = post.metadata.get("tags", [])
            tag_str = " ".join(f"#{t}" for t in tags[:3]) if tags else ""
            summary = (post.metadata.get("solution-summary") or post.metadata.get("description") or "")[:80]
            lines.append(f"- [{dt}] {title}  {tag_str}")
            if summary:
                lines.append(f"  └ {summary}")
        except Exception:
            lines.append(f"- [{dt}] {p.stem}")

    return "\n".join(lines)[:3000]


def collect_recent_audit(user_id: int, n: int = 3) -> str:
    """最近 N 次 care-agent 决策 · 让 AI 知道刚做过什么 · 不重复"""
    conn = db()
    rows = conn.execute(
        "SELECT fired_at, reasoning, should_engage, message, next_context "
        "FROM care_audit WHERE user_id=? ORDER BY fired_at DESC LIMIT ?",
        (user_id, n)
    ).fetchall()
    conn.close()

    if not rows:
        return "(还没有决策历史 · 你是第一次被唤醒)"

    lines = [f"# 最近 {n} 次决策"]
    for r in rows:
        dt = datetime.fromtimestamp(r["fired_at"], TZ).strftime("%m-%d %H:%M")
        engaged = "✅ 推送了" if r["should_engage"] else "⏸️ 没打扰"
        lines.append(f"- [{dt}] {engaged}")
        lines.append(f"  reasoning: {r['reasoning']}")
        if r["should_engage"]:
            lines.append(f"  message: {r['message'][:80]}")
        if r["next_context"]:
            lines.append(f"  当时预期: {r['next_context'][:80]}")
    return "\n".join(lines)[:1500]


# ────────── LLM 决策 ──────────

PROMPT = """你是 sift 的主动关心代理 (care-agent) · 你的工作:看用户的 vault 最近活动 + 当前时间 + 你上次的决策 · 判断**此刻**要不要给用户推一条关心消息。

## 当前时间
{now_str}(周{weekday} · {hour}:{minute:02d})

## 上次决策预期的场景
{last_context}

## 用户 vault 最近活动
{vault_activity}

## 你最近的决策历史
{recent_audit}

## 任务

输出严格 JSON · 只输出 JSON · 不要任何解释:

{{
  "reasoning": "你为啥这么决策(给用户看 audit · 100 字内)",
  "should_engage": <true 或 false>,
  "message": "如果 engage · 推给用户的话(像家人不像机器人 · 中文 · 150 字内)",
  "actions": ["push_telegram"],
  "next_trigger_minutes": <整数 · 多少分钟后再醒>,
  "next_context": "下次醒来你应该想什么(给未来的自己一句话提示)"
}}

## 风格 · 严格遵守

### message 字数:**≤ 30 字 · 2 句话内**

❌ 太长:
  "我刚部署完 sift care-agent · 现在是第一次给你推消息..."
  "你 vault 最近研究了 PRD v0.6 + 投喂入口 + 飞牛公网 SaaS..."

✅ 短而准:
  "还在敲呢 · 早点睡"
  "刚看你 PRD 写完 · 真的能跑了 · 睡吧"
  "PPT 还差 5 张 · 明天再改"

### 像家人 · 不像机器人

❌ 暴露机制/身份:
  - "我刚部署完" / "第一次给你推" / "我会再唤醒"
  - "sift care-agent" / "我是你的 AI 助手"
  - 任何把"机制"摆给用户看的话

❌ AI tone 词(立刻禁):
  - "密集处理" / "高能量输出" / "深度沉浸"
  - "持续输出" / "整理整合" / "梳理脉络"
  - "祝你..." / "希望..." / "加油"

✅ 真人腔:
  - 引用具体卡名 / 具体做的事(显你看到了)
  - 短句 · 口语 · 偶尔语气词("吧 · 呢 · 啊")
  - 像跟熟人发微信 · 不像写邮件

### reasoning 同样规则

reasoning 也是 ≤ 100 字 · 也要像真人写的 · 不要 AI tone。

### 不打扰原则

- 默认 should_engage = **false**(不打扰是默认)
- 凌晨 1-6 点 100% 不打扰
- 工作时间(9-18)没明显信号 → 不打扰
- 关心时机首选:早 7-9 / 中午 12-13 / 晚 21-23
- 同一天关心 ≤ 2 次

### next_trigger_minutes 建议

- 现在没什么 → 60-180(1-3 小时再看)
- 凌晨 → 设到早 7 点(精确算分钟数)
- 用户活跃期 → 30-60

### 绝对禁止

  - 早晚问安("早上好" / "晚安")
  - 营销话("升级 Plus" / "买点啥")
  - 抽象关心("注意身体" / "加油")
  - 暴露 sift 机制("我会再唤醒" / "我是 care-agent")
  - 自我介绍("我刚..." / "我看到了你的...")
"""


def call_llm(prompt: str) -> dict:
    """调 DeepSeek · JSON mode"""
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置")

    r = requests.post(
        LLM_API_URL,
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是 sift care-agent · 输出严格 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1500,
            "temperature": 0.4,
            "response_format": {"type": "json_object"},
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"].strip()

    # 容错:如果不是 JSON · 提取 JSON 块
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)

    return json.loads(text)


# ────────── 执行动作 ──────────

def push_telegram(message: str) -> bool:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ TG_BOT_TOKEN / TG_CHAT_ID 未配置 · 跳过推送")
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": TG_CHAT_ID,
                "text": f"💗 sift care\n\n{message}",
                "parse_mode": "Markdown",
            },
            timeout=15,
        )
        if r.ok:
            log(f"✅ Telegram 推送成功 · {len(message)} 字")
            return True
        else:
            log(f"⚠️ Telegram 推送失败: {r.status_code} {r.text[:200]}")
            return False
    except Exception as e:
        log(f"⚠️ Telegram 推送异常: {e}")
        return False


# ────────── 核心循环 ──────────

def log(msg: str):
    line = f"[{datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)


def run_once(user_id: int = DEFAULT_USER_ID, last_context: str = ""):
    """触发一次 · 拉数据 · 决策 · 执行 · schedule 下次"""
    init_db()
    now = datetime.now(TZ)
    log(f"🌅 care-agent fired · user={user_id} · last_context={last_context!r}")

    # 1. 收集数据 (per-user vault + audit)
    vault_activity = collect_vault_activity(user_id)
    recent_audit = collect_recent_audit(user_id)
    data_snapshot = {
        "vault_activity": vault_activity,
        "recent_audit": recent_audit,
        "now": now.isoformat(),
    }

    # 2. 调 LLM 决策
    weekday_zh = ["一", "二", "三", "四", "五", "六", "日"][now.weekday()]
    prompt = PROMPT.format(
        now_str=now.strftime("%Y-%m-%d %H:%M:%S"),
        weekday=weekday_zh,
        hour=now.hour,
        minute=now.minute,
        last_context=last_context or "(无 · 你是第一次或上次没设)",
        vault_activity=vault_activity,
        recent_audit=recent_audit,
    )

    try:
        decision = call_llm(prompt)
    except Exception as e:
        log(f"❌ LLM 调用失败: {e}")
        # 失败时也写 schedule · 30 分钟后再试
        schedule_next(user_id, 30, "LLM 失败后重试")
        return None

    log(f"🤖 decision: engage={decision.get('should_engage')} · next={decision.get('next_trigger_minutes')}min")
    log(f"   reasoning: {decision.get('reasoning', '')[:200]}")

    # 3. 写 audit
    conn = db()
    fired_at = int(now.timestamp())
    next_minutes = max(1, min(int(decision.get("next_trigger_minutes", 60)), 1440))  # 1 分钟到 24 小时
    next_trigger_at = fired_at + next_minutes * 60

    conn.execute("""
        INSERT INTO care_audit
        (user_id, fired_at, data_snapshot, reasoning, should_engage, message,
         actions, next_trigger_at, next_context, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id, fired_at,
        json.dumps(data_snapshot, ensure_ascii=False)[:5000],
        decision.get("reasoning", "")[:500],
        1 if decision.get("should_engage") else 0,
        (decision.get("message", "") or "")[:500],
        json.dumps(decision.get("actions", []), ensure_ascii=False),
        next_trigger_at,
        (decision.get("next_context", "") or "")[:500],
        fired_at,
    ))
    conn.commit()
    conn.close()

    # 4. 执行动作
    if decision.get("should_engage"):
        actions = decision.get("actions", [])
        for action in actions:
            if action == "push_telegram":
                push_telegram(decision.get("message", ""))

    # 5. schedule 下次
    schedule_next(user_id, next_minutes, decision.get("next_context", ""))
    next_dt = datetime.fromtimestamp(next_trigger_at, TZ).strftime("%m-%d %H:%M")
    log(f"⏰ next trigger: {next_dt} (in {next_minutes} min)")
    return decision


def schedule_next(user_id: int, minutes: int, context: str):
    """安排下次唤醒"""
    init_db()
    conn = db()
    # 取消所有 pending(只保留 1 个 next)
    conn.execute("UPDATE care_schedule SET state='cancelled' WHERE user_id=? AND state='pending'", (user_id,))
    trigger_at = int(time.time()) + minutes * 60
    conn.execute(
        "INSERT INTO care_schedule (user_id, trigger_at, context, state, created_at) "
        "VALUES (?, ?, ?, 'pending', ?)",
        (user_id, trigger_at, context, int(time.time()))
    )
    conn.commit()
    conn.close()


def check_due():
    """每分钟检查 · 有到时间的 schedule 就 fire"""
    init_db()
    conn = db()
    now_ts = int(time.time())
    rows = conn.execute(
        "SELECT id, user_id, context FROM care_schedule "
        "WHERE state='pending' AND trigger_at <= ?",
        (now_ts,)
    ).fetchall()
    if not rows:
        conn.close()
        return 0

    for r in rows:
        conn.execute("UPDATE care_schedule SET state='fired' WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()

    for r in rows:
        run_once(r["user_id"], r["context"])
    return len(rows)


def daemon():
    """主 daemon 循环 · 每 60 秒检查一次"""
    init_db()
    log("🟢 care-agent daemon 启动")

    # 检查是否有 pending schedule · 没有就立刻初始化一次
    conn = db()
    pending = conn.execute(
        "SELECT COUNT(*) FROM care_schedule WHERE state='pending'"
    ).fetchone()[0]
    conn.close()
    if pending == 0:
        log("📋 没有 pending schedule · 立刻初始化一次")
        run_once(DEFAULT_USER_ID, "(daemon 启动 · 第一次唤醒)")

    while True:
        try:
            fired = check_due()
            if fired:
                log(f"⏰ fired {fired} schedule(s)")
        except Exception as e:
            log(f"❌ daemon loop error: {e}")
        time.sleep(60)


# ────────── CLI ──────────

def main():
    parser = argparse.ArgumentParser(description="sift care-agent v1")
    parser.add_argument("--once", action="store_true", help="手动触发一次决策")
    parser.add_argument("--reset", action="store_true", help="清空 schedule + audit · 重新开始")
    parser.add_argument("--audit", action="store_true", help="查看最近 audit log")
    parser.add_argument("--schedule", action="store_true", help="查看当前 pending schedule")
    parser.add_argument("--user", type=int, default=DEFAULT_USER_ID, help="用户 ID(默认 1)")
    args = parser.parse_args()

    init_db()

    if args.reset:
        conn = db()
        conn.execute("DELETE FROM care_schedule")
        conn.execute("DELETE FROM care_audit")
        conn.commit()
        conn.close()
        print("✅ 已清空 care_schedule + care_audit")
        return

    if args.audit:
        conn = db()
        rows = conn.execute(
            "SELECT * FROM care_audit WHERE user_id=? ORDER BY fired_at DESC LIMIT 10",
            (args.user,)
        ).fetchall()
        conn.close()
        for r in rows:
            dt = datetime.fromtimestamp(r["fired_at"], TZ).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{dt}] engage={r['should_engage']}")
            print(f"  reasoning: {r['reasoning']}")
            if r['should_engage']:
                print(f"  message:   {r['message']}")
            print(f"  next:      {r['next_context']}")
        return

    if args.schedule:
        conn = db()
        rows = conn.execute(
            "SELECT * FROM care_schedule WHERE user_id=? ORDER BY trigger_at DESC LIMIT 5",
            (args.user,)
        ).fetchall()
        conn.close()
        for r in rows:
            dt = datetime.fromtimestamp(r["trigger_at"], TZ).strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{dt}] state={r['state']}  context={r['context']}")
        return

    if args.once:
        run_once(args.user, "(手动触发)")
        return

    # 默认 daemon 模式
    daemon()


if __name__ == "__main__":
    main()
