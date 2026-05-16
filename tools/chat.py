"""
sift chat · vault-aware AI 对话(SSE 流式)

设计:
  - classify_intent(msg) → "chat" | "ingest_url"(纯 URL / 投喂前缀 → ingest)
  - build_context(uid, query, history) → 系统提示 + retrieved 卡片 + 历史 + 用户问
  - stream_chat(...) → 异步生成 SSE event dict {event, data}
  - emit cite event: AI 输出 [[slug]] 时实时 emit
  - chat_sessions / chat_messages 表持久化

后端 SSE event types:
  meta  → {session_id, retrieved: [{slug,title,score,snippet}]}
  token → {delta: "..."}
  cite  → {slug: "..."}
  done  → {message_id, tokens_in, tokens_out, model}
  error → {code, message}
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import time
import uuid
from typing import AsyncIterator, Optional

import httpx

import retriever


# ────────── 配置 ──────────

LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-pro")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "8000"))

# Per-user vault path. Caller passes uid; we build the path on demand.
SIFT_USERS_ROOT = os.environ.get("SIFT_USERS_ROOT", "/vol1/1000/sift/users")


def _user_vault(uid: int) -> str:
    return f"{SIFT_USERS_ROOT}/{int(uid)}/vault"

URL_RE = re.compile(r"https?://[^\s]+")
INGEST_PREFIX = re.compile(r"^\s*(投喂|喂|存|加入|加|沉淀|\+)\s*[:：]?\s*(https?://)", re.IGNORECASE)
SLUG_CITE_RE = re.compile(r"\[\[([a-zA-Z0-9一-鿿぀-ヿ가-힯_\-]{2,80})\]\]")

SYSTEM_PROMPT_TEMPLATE = """你是 sift, 用户的"第二大脑"AI 助手。用户的笔记叫 vault, 每张笔记叫"卡"。

# 你的核心能力
回答用户的问题时, 主动引用用户 vault 里的相关卡片。引用方式: 在答案里嵌入 `[[卡片slug]]` 标记, 前端会自动转成可点击的引用 chip。

# 回答风格
- 中文为主, 直接 + 精炼, 不寒暄不空话
- 引用要自然嵌在句中, 不要"参考资料: ..."列表
- 如果 vault 没有相关卡, 大方说"vault 里没找到相关的, 我从一般知识答"

# 当前用户的 vault 检索结果
{retrieved_block}

# 用户消息
{user_message}
"""


# ────────── intent 分类 ──────────

def classify_intent(message: str) -> str:
    """轻量本地分类 · 不另调 LLM 省钱"""
    msg = (message or "").strip()
    if not msg:
        return "chat"
    # 纯 URL · 视为 ingest
    if URL_RE.fullmatch(msg):
        return "ingest_url"
    # 前缀触发(投喂 / + / 等)
    if INGEST_PREFIX.match(msg):
        return "ingest_url"
    # 单个 URL + 极短前后(<=10字非 URL 字符)· 也视为 ingest
    urls = URL_RE.findall(msg)
    if len(urls) == 1:
        non_url = URL_RE.sub("", msg).strip()
        if len(non_url) <= 10 and not re.search(r"[?？]$", msg):
            return "ingest_url"
    return "chat"


def extract_url(message: str) -> Optional[str]:
    urls = URL_RE.findall(message or "")
    return urls[0] if urls else None


# ────────── 上下文拼装 ──────────

def build_messages(
    user_message: str,
    retrieved: list[dict],
    history: list[dict],
) -> list[dict]:
    """组装 OpenAI 格式 messages · history 是 [{role, content}, ...]"""
    if retrieved:
        retrieved_block = ""
        for i, r in enumerate(retrieved, 1):
            tags = " ".join(f"#{t}" for t in (r.get("tags") or [])[:4])
            retrieved_block += (
                f"\n## 卡 {i} · {r['slug']}\n"
                f"标题: {r['title']}\n"
                f"{tags}\n"
                f"摘要/片段: {r.get('snippet','')}\n"
            )
    else:
        retrieved_block = "\n(vault 里没召回到相关卡片)\n"

    system = SYSTEM_PROMPT_TEMPLATE.format(
        retrieved_block=retrieved_block,
        user_message=user_message,
    )

    messages = [{"role": "system", "content": system}]
    # 历史(限制最近 6 轮 防超 token)
    for h in (history or [])[-12:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"][:4000]})
    messages.append({"role": "user", "content": user_message})
    return messages


# ────────── DeepSeek 流式调用 ──────────

async def stream_deepseek(
    messages: list[dict],
    model: str = None,
    api_url: str = None,
    api_key: str = None,
    max_tokens: int = None,
    temperature: float = 0.5,
) -> AsyncIterator[dict]:
    """yield {type: "delta"|"done"|"error", ...}"""
    api_url = api_url or LLM_API_URL
    api_key = api_key or LLM_API_KEY
    model = model or LLM_MODEL
    max_tokens = max_tokens or LLM_MAX_TOKENS
    if not api_key:
        yield {"type": "error", "code": "no_api_key", "message": "LLM_API_KEY 未配置"}
        return

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", api_url, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield {
                        "type": "error",
                        "code": f"upstream_{resp.status_code}",
                        "message": (body[:300].decode("utf-8", "ignore") if body else f"upstream {resp.status_code}"),
                    }
                    return
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        yield {"type": "done"}
                        return
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    try:
                        delta = chunk["choices"][0]["delta"].get("content")
                        if delta:
                            yield {"type": "delta", "content": delta}
                        usage = chunk.get("usage")
                        if usage:
                            yield {"type": "usage", "usage": usage}
                    except (KeyError, IndexError):
                        continue
    except httpx.RequestError as e:
        yield {"type": "error", "code": "network", "message": str(e)[:200]}
    except Exception as e:
        yield {"type": "error", "code": "internal", "message": str(e)[:200]}


# ────────── chat 主流程(异步生成 SSE event) ──────────

async def chat_stream(
    uid: int,
    message: str,
    session_id: Optional[str],
    history: list[dict],
    db_conn: sqlite3.Connection,
    byok: Optional[dict] = None,
) -> AsyncIterator[dict]:
    """
    yield {event: str, data: str(json)} 直接给 EventSourceResponse 用

    sse-starlette 的 EventSourceResponse 接收 dict {event, data, ...} 自动转 SSE 格式
    """
    if not session_id:
        session_id = uuid.uuid4().hex
        try:
            db_conn.execute(
                "INSERT OR IGNORE INTO chat_sessions(id, uid, title, mode, created_at, updated_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (session_id, uid, message[:40], "vault", int(time.time()), int(time.time())),
            )
            db_conn.commit()
        except Exception:
            pass

    # 1. 检索 vault (per-user isolation)
    try:
        retrieved = retriever.search(_user_vault(uid), message, top_k=6, uid=uid)
    except Exception:
        retrieved = []

    yield {
        "event": "meta",
        "data": json.dumps({
            "session_id": session_id,
            "retrieved": [
                {"slug": r["slug"], "title": r["title"], "score": r["score"]}
                for r in retrieved
            ],
        }, ensure_ascii=False),
    }

    # 2. 保存用户消息
    user_msg_id = uuid.uuid4().hex
    try:
        db_conn.execute(
            "INSERT INTO chat_messages(id, session_id, role, content, retrieved_slugs, "
            "tokens_in, tokens_out, cost_cny, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user_msg_id, session_id, "user", message,
                json.dumps([r["slug"] for r in retrieved]),
                0, 0, 0.0, int(time.time()),
            ),
        )
        db_conn.commit()
    except Exception:
        pass

    # 3. 拼 messages
    messages = build_messages(message, retrieved, history)

    # 4. 流式调用 LLM + 检测 [[slug]] 实时 emit cite
    full_text = ""
    cited_slugs: set[str] = set()
    used_byok = bool(byok and byok.get("api_key"))
    usage_info = {}

    api_url = byok.get("api_url") if used_byok else None
    api_key = byok.get("api_key") if used_byok else None
    model = byok.get("model") if used_byok else None

    async for chunk in stream_deepseek(
        messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
    ):
        if chunk["type"] == "delta":
            delta = chunk["content"]
            full_text += delta
            yield {"event": "token", "data": json.dumps({"delta": delta}, ensure_ascii=False)}
            # 检测新出现的 [[slug]] · 用累积文本扫
            for m in SLUG_CITE_RE.finditer(full_text):
                slug = m.group(1)
                if slug not in cited_slugs:
                    cited_slugs.add(slug)
                    yield {"event": "cite", "data": json.dumps({"slug": slug}, ensure_ascii=False)}
        elif chunk["type"] == "usage":
            usage_info = chunk.get("usage", {})
        elif chunk["type"] == "error":
            yield {"event": "error", "data": json.dumps(chunk, ensure_ascii=False)}
            return
        elif chunk["type"] == "done":
            break

    # 5. 保存 assistant 回复
    asst_msg_id = uuid.uuid4().hex
    tokens_in = int(usage_info.get("prompt_tokens", 0))
    tokens_out = int(usage_info.get("completion_tokens", 0))
    # DeepSeek V4 Pro: 缓存 0.5 元/1M input · 1.5 元/1M output (估)
    cost_cny = (tokens_in * 0.5 + tokens_out * 1.5) / 1_000_000
    try:
        db_conn.execute(
            "INSERT INTO chat_messages(id, session_id, role, content, retrieved_slugs, "
            "tokens_in, tokens_out, cost_cny, created_at) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                asst_msg_id, session_id, "assistant", full_text,
                json.dumps(list(cited_slugs)),
                tokens_in, tokens_out, cost_cny, int(time.time()),
            ),
        )
        db_conn.execute(
            "UPDATE chat_sessions SET updated_at=? WHERE id=?",
            (int(time.time()), session_id),
        )
        db_conn.commit()
    except Exception:
        pass

    yield {
        "event": "done",
        "data": json.dumps({
            "message_id": asst_msg_id,
            "session_id": session_id,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_cny": round(cost_cny, 5),
            "cited_slugs": list(cited_slugs),
            "byok_used": used_byok,
        }, ensure_ascii=False),
    }


# ────────── schema ──────────

def ensure_chat_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id TEXT PRIMARY KEY,
            uid INTEGER NOT NULL,
            title TEXT,
            mode TEXT DEFAULT 'vault',
            created_at INTEGER,
            updated_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_chat_sessions_uid ON chat_sessions(uid, updated_at DESC);

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT,
            retrieved_slugs TEXT,
            tokens_in INTEGER DEFAULT 0,
            tokens_out INTEGER DEFAULT 0,
            cost_cny REAL DEFAULT 0.0,
            created_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_session
            ON chat_messages(session_id, created_at);
    """)
    conn.commit()


def get_session_history(conn: sqlite3.Connection, session_id: str, uid: int, limit: int = 20) -> list[dict]:
    """加载会话的近 N 条消息(过滤 uid)"""
    if not session_id:
        return []
    rows = conn.execute(
        """SELECT m.role, m.content, m.created_at, m.retrieved_slugs
           FROM chat_messages m
           JOIN chat_sessions s ON s.id = m.session_id
           WHERE m.session_id = ? AND s.uid = ?
           ORDER BY m.created_at ASC LIMIT ?""",
        (session_id, uid, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def list_sessions(conn: sqlite3.Connection, uid: int, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT id, title, mode, created_at, updated_at FROM chat_sessions "
        "WHERE uid=? ORDER BY updated_at DESC LIMIT ?",
        (uid, limit),
    ).fetchall()
    return [dict(r) for r in rows]
