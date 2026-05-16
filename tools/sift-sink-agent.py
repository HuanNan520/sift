#!/usr/bin/env python3
"""Stop hook: AI-driven sift card sinking. Fire-and-forget.

On Stop event, fork a detached worker that:
1. Reads transcript jsonl (last ~120 messages)
2. Asks SiliconFlow DeepSeek-V3 whether this session deserves a sift card
3. If yes, generates frontmatter + body, writes ~/claude-journal/skills/{type}/
4. Lints the new card; quarantines on failure
5. Notifies Telegram of the new card

Recursion guard: SORA_SILENCE=1 short-circuits. Workers running `urllib`
calls don't trigger CC hooks (no nested claude CLI).
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import date
from pathlib import Path


if os.environ.get("SORA_SILENCE") == "1":
    sys.exit(0)


def _envpath(name: str, default: Path) -> Path:
    v = os.environ.get(name, "")
    return Path(v) if v else default


VAULT_ROOT = _envpath("SIFT_ROOT", Path.home() / "claude-journal")
VAULT_SKILLS = VAULT_ROOT / "skills"
QUARANTINE = VAULT_SKILLS / "_quarantine"
LOG_PATH = _envpath("SIFT_LOG_DIR", Path.home() / ".claude" / "hooks") / "sift-sink-agent.log"
SF_KEY_PATH = _envpath(
    "SIFT_SF_KEY_MEMORY",
    Path.home() / ".claude/projects/-home-huannan/memory/reference_siliconflow_api.md",
)
LINT_SH = _envpath("SIFT_LINT_BIN", Path("/mnt/e/带走/sift/lint.sh"))

SF_URL = os.environ.get("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
SF_MODEL = os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8000"))

VALID_TYPES = {"debug", "scripts", "decisions", "research"}


def log(msg: str):
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def load_sf_key() -> str:
    # env priority: LLM_API_KEY (generic, current provider) > DEEPSEEK_API_KEY > SILICONFLOW_API_KEY
    for var in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
        v = os.environ.get(var, "")
        if v.startswith("sk-"):
            return v
    # fallback: memory .md file regex (WSL legacy)
    if not SF_KEY_PATH.exists():
        return ""
    try:
        content = SF_KEY_PATH.read_text(encoding="utf-8")
        m = re.search(r"\*\*Key\*\*:\s*`(sk-[^`]+)`", content)
        return m.group(1) if m else ""
    except Exception as e:
        log(f"load_sf_key fail: {e}")
        return ""


def slugify(s: str, max_len: int = 40) -> str:
    if not s:
        return "session"
    s = re.sub(r"\s+", "-", s.strip())
    # 允许 CJK + 拉丁 + 数字 + . _ -;sift schema 接受 CJK 区段
    s = re.sub(r"[^\w　-ヿ一-鿿가-힯\.\-]", "", s)
    s = re.sub(r"-+", "-", s).strip("-._")
    return s[:max_len] or "session"


def read_transcript(jsonl_path: str, max_msgs: int = 120) -> list:
    msgs = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                t = msg.get("type")
                if t not in ("user", "assistant"):
                    continue
                content = msg.get("message", {}).get("content", "")
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        if "text" in c:
                            parts.append(c["text"])
                        elif c.get("type") == "tool_use":
                            parts.append(f"[tool: {c.get('name', '?')}]")
                        elif c.get("type") == "tool_result":
                            parts.append("[tool_result]")
                    content = " ".join(parts)
                if isinstance(content, str) and content.strip():
                    cap = 3000 if t == "assistant" else 1500
                    msgs.append({"role": t, "content": content[:cap]})
    except Exception as e:
        log(f"read_transcript fail: {e}")
    return msgs[-max_msgs:]


SYSTEM_PROMPT = """你是 sift 沉淀判官。读完下面这段 Claude Code session 对话,判断要不要沉淀成 sift 卡片。

## 重要

**只看 session 主线最近发生的事**,不要从 transcript 早期内容编故事。
**只用对话里出现过的具体名词**,不要把 memory 里的旧项目硬塞进卡里。
**如果 session 在做 A,你不要去写 B 的卡**,即使 transcript 早段提到过 B。

触发门槛(任一即触发):
- debug: 非平凡 bug,诊断+修 >5min,有具体 root cause + 解法
- scripts: >10 行可复用代码,带非显然 flag / setup
- decisions: 在 2+ 架构/流程方案之间做了选择,带 load-bearing rationale
- research: >30min 调研、并行 agent、多源

不沉淀(YAGNI):
- 单次 cat / ls / find / grep / mv 命令
- "X 是什么"答完即弃
- 已在 ~/.claude/memory/ 的简短事实
- 第一次撞到的事(没复用价值)
- 没具体行动只闲聊
- session 还在进行中没结论

输出严格 JSON(无 markdown 包裹,无任何解释)。

不沉淀: {"sink": false}

沉淀:
{
  "sink": true,
  "type": "debug|scripts|decisions|research",
  "slug": "短-slug-CJK-OK,5-30字符",
  "frontmatter": {完整 frontmatter,按 type 走 schema},
  "body": "完整 markdown 正文,按章节结构"
}

frontmatter 硬约束:
- date: 今天日期(传入,不要乱编)
- ai-first: true
- audience: claude
- tags: 数组,>=1 项,允许中日韩字符
- research 必填: problem + solution-summary + expires (date+3月,YYYY-MM-DD 字符串) + recheck-trigger (数组,>=1)
- debug 必填: problem + solution-summary
- scripts 必填: purpose
- decisions 必填: context + choice
- 字符串字段含 # : ' " [ ] 等特殊字符时不用 quote,YAML 引用工具会处理
- 不要凭空发明项目名 / 工具版本号 / 文件路径,只用对话里出现过的
- result_chip 可选(写卡时判,不确定就 null): 用户在 sift APP 上看到这张卡时的"结果标签"
  - "盲点"     = 卡片帮用户指出他没想到的点 / 提醒上次没注意 / 发现的漏洞
  - "复盘"     = 卡片整理过去事件 / 旧案 / 历史方案 / 跨案关联
  - "替做"     = sift 替用户做了某件事(自动整理周报 / 生成 PPT / 自动归档 / 跨设备同步推送)
  - "坑提醒"   = 标记用户已经否过的方案 / 已知失败路径 / 别再重复犯错
  - null      = 不属于以上 4 类,或不确定

正文章节(必须按顺序):
- debug: ## For future Claude / ## Problem / ## Root Cause / ## Solution / ## Pitfalls
- scripts: ## For future Claude / ## Usage / ## Code / ## Dependencies / ## Why / ## Pitfalls
- decisions: ## For future Claude / ## Context / ## Options Considered / ## Choice + Rationale / ## Consequences / ## Reconsider when
- research: ## For future Claude / ## Problem / ## Method / ## Findings / ## Sources / ## Recheck protocol
"""


def call_llm(transcript_text: str, today_str: str, timeout: int = 120) -> dict | None:
    key = load_sf_key()
    if not key:
        log("call_llm: no SF key")
        return None

    user_msg = (
        f"今天日期: {today_str}\n\n"
        f"--- session transcript ---\n\n{transcript_text}"
    )
    body = json.dumps({
        "model": SF_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")

    req = urllib.request.Request(
        SF_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
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


def send_tg(text: str):
    # MUTED 2026-05-13 · care-agent 接管推送 · sink-agent 不再每张卡都推
    return
    token = os.environ.get("TG_BOT_TOKEN", "")
    chat_id = os.environ.get("TG_CHAT_ID", "")
    if not token or not chat_id:
        log("send_tg: no TG env")
        return
    try:
        body = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        urllib.request.urlopen(
            urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=10,
        )
    except Exception as e:
        log(f"send_tg fail: {e}")


def _yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "":
        return "''"
    if (re.search(r'[#:\'"\[\]{}|>&*!%@`,]', s) or
            re.match(r'^\d{4}-\d{2}-\d{2}$', s) or
            s.lower() in ('true', 'false', 'null', 'yes', 'no', '~')):
        return "'" + s.replace("'", "''") + "'"
    return s


def yaml_dump_simple(fm: dict) -> str:
    lines = []
    for k, v in fm.items():
        if isinstance(v, list):
            lines.append(f"{k}:")
            for item in v:
                lines.append(f"  - {_yaml_scalar(item)}")
        elif isinstance(v, dict):
            lines.append(f"{k}:")
            for ck, cv in v.items():
                lines.append(f"  {ck}: {_yaml_scalar(cv)}")
        else:
            lines.append(f"{k}: {_yaml_scalar(v)}")
    return "\n".join(lines)


def write_card(card: dict, today_str: str) -> Path | None:
    card_type = card.get("type")
    raw_slug = card.get("slug", "session")
    slug = slugify(raw_slug)
    fm = dict(card.get("frontmatter", {}))
    body = card.get("body", "")

    if card_type not in VALID_TYPES:
        log(f"write_card: invalid type {card_type}")
        return None

    # Merge top-level fields into frontmatter (LLM 常把 type 放顶层而不是 fm 里)
    fm.setdefault("type", card_type)
    fm.setdefault("date", today_str)
    fm.setdefault("ai-first", True)
    fm.setdefault("audience", "claude")
    # type 字段必须排第一位(可读性)
    fm = {"type": fm["type"], **{k: v for k, v in fm.items() if k != "type"}}

    target_dir = VAULT_SKILLS / card_type
    target_dir.mkdir(parents=True, exist_ok=True)

    base = f"{today_str}-{slug}"
    target = target_dir / f"{base}.md"
    i = 2
    while target.exists():
        target = target_dir / f"{base}-{i}.md"
        i += 1

    content = f"---\n{yaml_dump_simple(fm)}\n---\n\n{body.rstrip()}\n"
    try:
        target.write_text(content, encoding="utf-8")
        return target
    except Exception as e:
        log(f"write_card fail: {e}")
        return None


def lint_card(card_path: Path) -> bool:
    if not LINT_SH.exists():
        log("lint_card: lint.sh missing, skip")
        return True
    try:
        result = subprocess.run(
            [str(LINT_SH), str(Path.home() / "claude-journal")],
            capture_output=True, text=True, timeout=60,
        )
        out = result.stdout + result.stderr
        # 看新写的卡是否在 failures 段
        if card_path.name in out and ("is a required property" in out or
                                       "does not match" in out or
                                       "Failed" in out):
            log(f"lint_card: {card_path.name} failed\n{out[-600:]}")
            return False
        return True
    except Exception as e:
        log(f"lint_card exception: {e}")
        return True  # 不阻塞


def quarantine(card_path: Path):
    try:
        QUARANTINE.mkdir(parents=True, exist_ok=True)
        target = QUARANTINE / card_path.name
        i = 2
        while target.exists():
            target = QUARANTINE / f"{card_path.stem}-{i}{card_path.suffix}"
            i += 1
        card_path.rename(target)
        log(f"quarantined → {target}")
    except Exception as e:
        log(f"quarantine fail: {e}")


def worker(payload_str: str):
    try:
        payload = json.loads(payload_str or "{}")
    except Exception as e:
        log(f"worker: bad payload: {e}")
        return

    transcript_path = payload.get("transcript_path") or ""
    session_id = payload.get("session_id") or payload.get("sessionId") or ""

    if not transcript_path or not Path(transcript_path).is_file():
        log(f"worker: no transcript at '{transcript_path}'")
        return

    messages = read_transcript(transcript_path, max_msgs=50)
    if not messages:
        log("worker: empty transcript")
        return

    transcript_text = "\n\n".join(
        f"[{m['role']}]\n{m['content']}" for m in messages
    )

    today_str = date.today().strftime("%Y-%m-%d")
    judgment = call_llm(transcript_text, today_str)
    if judgment is None:
        log("worker: no judgment")
        return

    if not judgment.get("sink"):
        log(f"worker: not sink (session={session_id[:12]})")
        return

    if os.environ.get("SIFT_SINK_DRY_RUN") == "1":
        log(f"worker: DRY_RUN sink={judgment.get('type')}/{judgment.get('slug')}")
        print(json.dumps(judgment, ensure_ascii=False, indent=2), file=sys.stderr)
        return

    card_path = write_card(judgment, today_str)
    if not card_path:
        return

    if not lint_card(card_path):
        quarantine(card_path)
        send_tg(f"⚠️ sift-sink: lint failed, quarantined `{card_path.name}`")
        return

    log(f"worker: wrote {card_path}")
    fm = judgment.get("frontmatter", {})
    problem_line = (fm.get("problem") or fm.get("context") or fm.get("purpose")
                    or fm.get("solution-summary") or "")
    problem_line = str(problem_line)[:200]
    try:
        rel = card_path.relative_to(Path.home())
        path_str = f"~/{rel}"
    except ValueError:
        path_str = str(card_path)
    send_tg(
        f"📌 *sift sink* `{judgment.get('type')}` `{judgment.get('slug')}`\n"
        f"`{path_str}`\n"
        f"{problem_line}"
    )


def main():
    payload_str = sys.stdin.read() if not sys.stdin.isatty() else ""

    if "--worker" in sys.argv:
        try:
            worker(payload_str)
        except Exception as e:
            log(f"worker top-level: {e}")
        return

    if "--dry-run" in sys.argv:
        os.environ["SIFT_SINK_DRY_RUN"] = "1"
        try:
            worker(payload_str)
        except Exception as e:
            log(f"dry-run top-level: {e}")
        return

    # parent: fork worker, return immediately
    try:
        proc = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env={**os.environ},
        )
        proc.stdin.write(payload_str.encode("utf-8"))
        proc.stdin.close()
    except Exception as e:
        log(f"parent: fork failed: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"top-level: {e}")
