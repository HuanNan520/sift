#!/usr/bin/env python3
"""
sift FastAPI backend · 飞牛上跑 · 通过 VMRack Caddy 反代 → sift.echovale.online
"""
from fastapi import FastAPI, HTTPException, Request, Form, Depends, Body
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Optional
import frontmatter
import markdown
import sqlite3
import secrets
import time
import os
import re
import io
import json
import base64
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from ingest import ingest_url
except Exception as _ingest_err:
    ingest_url = None
    _INGEST_IMPORT_ERROR = str(_ingest_err)
else:
    _INGEST_IMPORT_ERROR = None

from auth import (
    ensure_auth_schema,
    current_user, current_user_optional,
    create_access_token, create_refresh_token,
    lookup_refresh_token, rotate_refresh_token, revoke_refresh_token,
    revoke_all_refresh_tokens,
    create_user, get_user_by_email, get_user_by_id, touch_login,
    verify_password, needs_rehash, hash_password,
    get_user_plan, get_quota_used,
)
import chat as chat_module
import retriever
import quota as quota_module
from sse_starlette.sse import EventSourceResponse

SIFT_USERS_ROOT = Path(os.environ.get("SIFT_USERS_ROOT", "/vol1/1000/sift/users"))
SIFT_USERS_ROOT.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.environ.get("SIFT_DB", "/vol1/1000/sift/sift.sqlite"))
BASE_URL = os.environ.get("SIFT_BASE_URL", "https://sift.echovale.online")


# ────────── 多租户隔离 helpers (v1 SaaS) ──────────
# 每个用户的 vault / _reports / _audit 物理隔离在 SIFT_USERS_ROOT/{uid}/ 下。
# 这取代了原来全局共享的 SIFT_ROOT,任何 endpoint 走 file system 都要先拿 uid。

def get_user_vault(uid: int) -> Path:
    """{users}/{uid}/vault — 卡片 markdown 主存储。自动创建。"""
    p = SIFT_USERS_ROOT / str(int(uid)) / "vault"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_user_reports(uid: int) -> Path:
    """{users}/{uid}/_reports — 周报 / 日报输出目录。"""
    p = SIFT_USERS_ROOT / str(int(uid)) / "_reports"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_user_audit(uid: int) -> Path:
    """{users}/{uid}/_audit — care-agent 审计日志、ingest 历史。"""
    p = SIFT_USERS_ROOT / str(int(uid)) / "_audit"
    p.mkdir(parents=True, exist_ok=True)
    return p


def iter_user_dirs():
    """Yield (uid:int, vault_path:Path) for every user under SIFT_USERS_ROOT
    that has a vault directory. Used by startup index builder and global
    aggregates that need to walk every tenant."""
    if not SIFT_USERS_ROOT.exists():
        return
    for udir in SIFT_USERS_ROOT.iterdir():
        if not udir.is_dir() or not udir.name.isdigit():
            continue
        vault = udir / "vault"
        if vault.exists():
            yield int(udir.name), vault

app = FastAPI(title="sift", description="AI 知识库 · 沉淀你的每一段思考")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 早期 alpha · APP 上线后改 tauri://localhost + https://sift.echovale.online
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# v0.6 · 关键文件强制 no-cache(防 CF 缓存锁老 HTML / SW)
_NO_CACHE_PATHS = {
    "/", "/index.html", "/sw.js", "/manifest.json",
    "/landing.html", "/download.html", "/download", "/welcome",
    "/app", "/app/", "/app/index.html",
    "/auth.js", "/chat.js", "/v06.css", "/api.js", "/offline.js",
    "/api/version", "/api/auth/me", "/api/quota",
}


@app.middleware("http")
async def force_no_cache(request: Request, call_next):
    response = await call_next(request)
    if request.url.path in _NO_CACHE_PATHS:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            phone TEXT,
            invite_code TEXT UNIQUE,
            invited_by TEXT,
            tier TEXT DEFAULT 'free',
            created_at INTEGER,
            telegram_chat_id TEXT
        );
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact TEXT NOT NULL,
            channel TEXT,
            reason TEXT,
            created_at INTEGER,
            user_agent TEXT
        );
        CREATE TABLE IF NOT EXISTS share_views (
            slug TEXT,
            viewer_ip TEXT,
            referrer TEXT,
            ua TEXT,
            ts INTEGER
        );
    """)
    conn.commit()
    conn.close()


init_db()
# v0.6 auth schema 扩展(users 加列 + plans/refresh_tokens 表)
_init_conn = db()
ensure_auth_schema(_init_conn)
chat_module.ensure_chat_schema(_init_conn)
_init_conn.close()
# 启动时为每个已存在用户预建 retriever 索引。
# Per-tenant since each user has an isolated vault.
try:
    _built = 0
    for _uid, _vault in iter_user_dirs():
        try:
            retriever.build_index(_vault, force=True)
            _built += 1
        except Exception as _e:
            print(f"[retriever] uid={_uid} 索引失败: {_e}")
    print(f"[retriever] 启动时为 {_built} 个用户建索引完成")
except Exception as _e:
    print(f"[retriever] 启动扫用户目录失败: {_e}")


# ────────── 卡片渲染辅助 ──────────

_SLUG_RE = re.compile(r"^[a-zA-Z0-9一-龥぀-ヿ가-힯_-]{1,80}$")


def find_card_file(uid: int, slug: str) -> Path | None:
    """在用户 uid 自己的 vault 里按 slug 找 markdown 文件(支持子目录)。
    返回 None 表示不存在或 slug 不合规。永不跨用户。"""
    if not _SLUG_RE.match(slug):
        return None
    vault = get_user_vault(uid)
    for path in vault.rglob(f"{slug}.md"):
        return path
    return None


def find_public_card_file(slug: str) -> tuple[int, Path] | None:
    """跨所有用户找标记 public: true 的 slug 对应卡片(用于 /c/{slug} 公开分享)。
    扫到第一张匹配且 frontmatter public=true 的卡返回 (uid, path)。
    没匹配返回 None。"""
    if not _SLUG_RE.match(slug):
        return None
    for uid, vault in iter_user_dirs():
        for p in vault.rglob(f"{slug}.md"):
            try:
                post = frontmatter.load(p)
                if post.metadata.get("public") is True:
                    return uid, p
            except Exception:
                continue
    return None


def render_card_html(slug: str, post: frontmatter.Post, tier: str = "free") -> str:
    """渲染 markdown 卡片成完整 HTML 页面 · Free 带水印"""
    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc", "nl2br"])
    body_html = md.convert(post.content)
    title = post.metadata.get("title", slug)
    desc = post.metadata.get("description") or post.metadata.get("solution-summary", "")
    tags = post.metadata.get("tags", [])
    date = post.metadata.get("date", "")

    # OG meta(微信 / 朋友圈 / Twitter 预览)
    og_meta = f'''
    <meta property="og:title" content="{title}" />
    <meta property="og:description" content="{desc[:200]}" />
    <meta property="og:url" content="{BASE_URL}/c/{slug}" />
    <meta property="og:type" content="article" />
    <meta name="twitter:card" content="summary" />
    '''

    # 水印 footer(Free 用户)
    watermark = '''
    <div class="sift-watermark">
      <div class="sift-watermark-card">
        <div class="brand">
          <span class="logo">📚</span>
          <span class="name">sift</span>
        </div>
        <div class="tagline">
          AI 帮你沉淀每一段思考
        </div>
        <a class="cta" href="https://sift.echovale.online" target="_blank">
          立即免费试用 →
        </a>
        <div class="hint">数据完全你的 · 随时可带走 · 开源 + SaaS 双轨</div>
      </div>
    </div>
    ''' if tier == "free" else ""

    tag_html = " ".join(f'<span class="tag">#{t}</span>' for t in tags) if tags else ""

    return f'''<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} · sift</title>
{og_meta}
<style>
  :root {{
    --bg: #F7F4EE;
    --surface: #FFFFFF;
    --ink: #1B1614;
    --ink-2: #5C544D;
    --accent: #2E5BFF;
    --warm: #D9783A;
    --border: rgba(27,22,20,.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", "Source Han Sans SC", sans-serif;
    background: var(--bg);
    color: var(--ink);
    line-height: 1.7;
  }}
  .container {{
    max-width: 720px;
    margin: 0 auto;
    padding: 48px 24px 0;
  }}
  .meta {{
    color: var(--ink-2);
    font-size: 14px;
    margin-bottom: 12px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
  }}
  .tag {{
    background: rgba(46,91,255,.10);
    color: var(--accent);
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
  }}
  h1 {{ font-size: 32px; font-weight: 600; margin: 0 0 24px; letter-spacing: -0.018em; }}
  h2 {{ font-size: 22px; font-weight: 600; margin: 32px 0 16px; }}
  h3 {{ font-size: 18px; font-weight: 600; margin: 24px 0 12px; }}
  p {{ margin: 12px 0; }}
  code {{
    font-family: "SF Mono", Menlo, monospace;
    background: rgba(27,22,20,.06);
    padding: 2px 6px;
    border-radius: 4px;
    font-size: .92em;
  }}
  pre {{
    background: #1B1614;
    color: #F4EFE5;
    padding: 16px;
    border-radius: 12px;
    overflow-x: auto;
  }}
  pre code {{ background: none; color: inherit; padding: 0; }}
  blockquote {{
    border-left: 3px solid var(--accent);
    padding: 4px 0 4px 16px;
    margin: 16px 0;
    color: var(--ink-2);
  }}
  table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
  th, td {{ border: 1px solid var(--border); padding: 8px 12px; text-align: left; }}
  th {{ background: rgba(27,22,20,.04); }}
  a {{ color: var(--accent); }}
  hr {{ border: none; border-top: 1px solid var(--border); margin: 32px 0; }}

  .sift-watermark {{
    background: linear-gradient(180deg, transparent 0%, rgba(46,91,255,.04) 100%);
    padding: 48px 24px 64px;
    margin-top: 48px;
    border-top: 1px solid var(--border);
  }}
  .sift-watermark-card {{
    max-width: 480px;
    margin: 0 auto;
    background: var(--surface);
    border-radius: 16px;
    padding: 32px 24px;
    text-align: center;
    box-shadow: 0 1px 2px rgba(27,22,20,.04), 0 8px 24px rgba(27,22,20,.06);
  }}
  .sift-watermark .brand {{
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    margin-bottom: 8px;
  }}
  .sift-watermark .logo {{ font-size: 28px; }}
  .sift-watermark .name {{ font-size: 24px; font-weight: 700; color: var(--ink); }}
  .sift-watermark .tagline {{
    color: var(--ink-2);
    font-size: 15px;
    margin-bottom: 24px;
  }}
  .sift-watermark .cta {{
    display: inline-block;
    background: var(--accent);
    color: white;
    text-decoration: none;
    padding: 14px 32px;
    border-radius: 999px;
    font-weight: 600;
    margin-bottom: 16px;
    transition: transform .14s;
  }}
  .sift-watermark .cta:hover {{ transform: translateY(-1px); }}
  .sift-watermark .hint {{ color: var(--ink-2); font-size: 12px; }}
</style>
</head>
<body>
<article class="container">
  <div class="meta">
    {f'<span>{date}</span>' if date else ''}
    {tag_html}
  </div>
  <h1>{title}</h1>
  {body_html}
</article>
{watermark}
</body>
</html>'''


# ────────── 路由 ──────────

@app.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"


@app.get("/apple-touch-icon.svg")
async def apple_touch_icon():
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
<rect width="512" height="512" rx="112" fill="#2E5BFF"/>
<text x="50%" y="62%" text-anchor="middle" font-size="280" font-family="-apple-system,sans-serif" fill="white">📚</text>
</svg>'''
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/manifest.json")
async def manifest():
    """PWA manifest · v0.6 start_url=/app/ + PNG icons"""
    return JSONResponse({
        "name": "Sift",
        "short_name": "Sift",
        "description": "你的第二大脑 · vault-aware AI 对话",
        "start_url": "/app/?source=pwa",
        "scope": "/app/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#F7F4EE",
        "theme_color": "#F7F4EE",
        "lang": "zh-CN",
        "categories": ["productivity", "utilities"],
        "icons": [
            {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
            {"src": "/icon-1024.png", "sizes": "1024x1024", "type": "image/png", "purpose": "any maskable"},
        ],
    })


@app.get("/welcome", response_class=HTMLResponse)
async def welcome(request: Request):
    """营销主页 · /welcome · 从 B 站简介 / 邀请链接进来看的"""
    # Aggregate across all tenants for the public marketing counter.
    card_count = 0
    vault_size_mb = 0.0
    for _uid, _vault in iter_user_dirs():
        for f in _vault.rglob("*.md"):
            try:
                card_count += 1
                vault_size_mb += f.stat().st_size / 1024 / 1024
            except FileNotFoundError:
                continue
    return HOME_HTML.format(
        card_count=card_count,
        vault_size_mb=int(vault_size_mb),
    )


@app.get("/c/{slug}", response_class=HTMLResponse)
async def view_card(slug: str, request: Request):
    """卡片公开渲染 · 仅 frontmatter `public: true` 的卡可被任何人看。
    其他卡只能通过登录后调 /api/cards/{slug} 拿到。"""
    found = find_public_card_file(slug)
    if not found:
        raise HTTPException(404, "Card not found (or not public)")
    _uid, path = found
    try:
        post = frontmatter.load(path)
    except Exception:
        raise HTTPException(500, "Card parse failed")
    # 记录浏览
    try:
        conn = db()
        conn.execute(
            "INSERT INTO share_views (slug, viewer_ip, referrer, ua, ts) VALUES (?, ?, ?, ?, ?)",
            (slug, request.client.host if request.client else "",
             request.headers.get("referer", ""), request.headers.get("user-agent", ""), int(time.time()))
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return HTMLResponse(render_card_html(slug, post, tier="free"))


# ────────── 账号系统(v0.6) ──────────

def _serialize_user(u: dict) -> dict:
    """对前端的安全字段(剔除 pwd_hash / byok_blob)"""
    return {
        "uid": u["id"],
        "email": u["email"],
        "plan_id": u.get("plan_id") or 1,
        "tier": u.get("tier") or "free",
        "invite_code": u.get("invite_code"),
        "created_at": u.get("created_at"),
        "last_login_at": u.get("last_login_at"),
    }


@app.post("/api/auth/register", response_class=JSONResponse)
async def auth_register(
    email: str = Form(...),
    password: str = Form(...),
    invite: str = Form(default=""),
    request: Request = None,
):
    """注册 · 邮箱 + 密码 · 不强制邮件激活 · 返 access+refresh"""
    email = email.lower().strip()
    if not email or "@" not in email or len(email) > 200:
        return JSONResponse({"ok": False, "error": "邮箱格式不对"}, 400)
    if len(password) < 6:
        return JSONResponse({"ok": False, "error": "密码至少 6 字符"}, 400)
    if len(password) > 256:
        return JSONResponse({"ok": False, "error": "密码过长"}, 400)
    conn = db()
    try:
        user = create_user(conn, email, password, invited_by=invite.strip() or None)
    except ValueError as e:
        conn.close()
        return JSONResponse({"ok": False, "error": str(e)}, 400)
    access = create_access_token(user["id"], user.get("plan_id") or 1)
    ua = (request.headers.get("user-agent", "")[:200]) if request else ""
    refresh = create_refresh_token(conn, user["id"], ua)
    conn.close()
    return {
        "ok": True,
        "user": _serialize_user(user),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }


@app.post("/api/auth/login", response_class=JSONResponse)
async def auth_login(
    email: str = Form(...),
    password: str = Form(...),
    request: Request = None,
):
    """登录 · 返 access+refresh · 密码错统一返"邮箱或密码错"避免枚举攻击"""
    email = email.lower().strip()
    conn = db()
    user = get_user_by_email(conn, email)
    if not user or not user.get("pwd_hash"):
        conn.close()
        return JSONResponse({"ok": False, "error": "邮箱或密码错"}, 401)
    if not verify_password(password, user["pwd_hash"]):
        conn.close()
        return JSONResponse({"ok": False, "error": "邮箱或密码错"}, 401)
    # 自动 argon2 升级(参数变了重算)
    if needs_rehash(user["pwd_hash"]):
        try:
            conn.execute("UPDATE users SET pwd_hash=? WHERE id=?",
                         (hash_password(password), user["id"]))
            conn.commit()
        except Exception:
            pass
    touch_login(conn, user["id"])
    access = create_access_token(user["id"], user.get("plan_id") or 1)
    ua = (request.headers.get("user-agent", "")[:200]) if request else ""
    refresh = create_refresh_token(conn, user["id"], ua)
    user = get_user_by_id(conn, user["id"])
    conn.close()
    return {
        "ok": True,
        "user": _serialize_user(user),
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }


@app.post("/api/auth/refresh", response_class=JSONResponse)
async def auth_refresh(
    refresh_token: str = Form(...),
    request: Request = None,
):
    """换 access · 轮转 refresh(撤旧发新)"""
    conn = db()
    ua = (request.headers.get("user-agent", "")[:200]) if request else ""
    result = rotate_refresh_token(conn, refresh_token, ua)
    if not result:
        conn.close()
        return JSONResponse({"ok": False, "error": "refresh 无效或已过期 · 请重新登录"}, 401)
    uid, new_refresh = result
    user = get_user_by_id(conn, uid)
    conn.close()
    if not user:
        return JSONResponse({"ok": False, "error": "用户不存在"}, 401)
    access = create_access_token(uid, user.get("plan_id") or 1)
    return {
        "ok": True,
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@app.post("/api/auth/logout", response_class=JSONResponse)
async def auth_logout(
    refresh_token: str = Form(default=""),
    all_devices: bool = Form(default=False),
    user: dict = Depends(current_user_optional),
):
    """登出 · 撤销当前 refresh(默认)或全部 refresh(all_devices=true)"""
    conn = db()
    if all_devices and user:
        revoke_all_refresh_tokens(conn, user["uid"])
    elif refresh_token:
        revoke_refresh_token(conn, refresh_token)
    conn.close()
    return {"ok": True}


@app.get("/api/auth/me", response_class=JSONResponse)
async def auth_me(user: dict = Depends(current_user)):
    """验 token + 返当前用户 + 配额"""
    conn = db()
    u = get_user_by_id(conn, user["uid"])
    if not u:
        conn.close()
        raise HTTPException(404, "用户不存在")
    plan = get_user_plan(conn, user["uid"]) or {}
    quota = get_quota_used(conn, user["uid"])
    conn.close()
    return {
        "ok": True,
        "user": _serialize_user(u),
        "plan": {
            "id": plan.get("id"),
            "code": plan.get("code"),
            "name": plan.get("name"),
            "price_cny": plan.get("price_cny"),
            "quota_ingest_day": plan.get("quota_ingest_day"),
            "quota_chat_day": plan.get("quota_chat_day"),
            "quota_cards_total": plan.get("quota_cards_total"),
        },
        "quota_used": quota,
    }


@app.get("/api/quota", response_class=JSONResponse)
async def api_quota(user: dict = Depends(current_user)):
    """单独的 quota endpoint · 前端配额条用 · 比 /me 轻"""
    conn = db()
    snap = quota_module.get_quota_snapshot(conn, user["uid"])
    conn.close()
    return {"ok": True, **snap}


@app.get("/api/version", response_class=JSONResponse)
async def api_version():
    """SW versionCheck 用 · 不匹配触发强更新"""
    return {
        "cache_version": "sift-v0.6.0",
        "build_at": "2026-05-13",
        "api_version": "0.6.0",
    }


# ────────── chat · vault-aware SSE 流式 ──────────

@app.post("/api/chat")
async def api_chat(
    payload: dict = Body(...),
    user: dict = Depends(current_user),
    request: Request = None,
):
    """SSE 流式 chat · 检索 vault → DeepSeek V4 Pro → token + [[slug]] 引用"""
    message = (payload.get("message") or "").strip()
    session_id = payload.get("session_id")
    byok = payload.get("byok")
    if not message:
        return JSONResponse({"ok": False, "error": "message 不能为空"}, 400)
    if len(message) > 8000:
        return JSONResponse({"ok": False, "error": "message 过长(>8000)"}, 400)

    # intent 分类
    intent = chat_module.classify_intent(message)
    if intent == "ingest_url":
        if ingest_url is None:
            return JSONResponse({"ok": False, "error": "投喂模块加载失败"}, 500)
        # 扣 ingest 配额(不扣 chat)
        _q_conn = db()
        try:
            quota_module.check_and_consume(_q_conn, user["uid"], "ingest")
        finally:
            _q_conn.close()
        url = chat_module.extract_url(message)
        try:
            result = ingest_url(url, uid=user["uid"])
            retriever.invalidate_index()
            return JSONResponse({
                "ok": True,
                "intent": "ingest_url",
                "slug": result["slug"],
                "title": result["title"],
                "platform": result["platform"],
                "share_url": f"{BASE_URL}/c/{result['slug']}",
            })
        except Exception as e:
            return JSONResponse({"ok": False, "error": str(e)[:300]}, 500)

    # chat 流程 · BYOK 不扣配额(用户自己 key)· server-side 默认扣额
    used_byok = bool(payload.get("byok") and payload["byok"].get("api_key"))
    if not used_byok:
        _q_conn = db()
        try:
            quota_module.check_and_consume(_q_conn, user["uid"], "chat")
        finally:
            _q_conn.close()

    # chat 流程 · 加载历史
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    history_rows = chat_module.get_session_history(conn, session_id, user["uid"]) if session_id else []
    history = [{"role": r["role"], "content": r["content"]} for r in history_rows]

    async def generator():
        try:
            async for event_dict in chat_module.chat_stream(
                uid=user["uid"],
                message=message,
                session_id=session_id,
                history=history,
                db_conn=conn,
                byok=byok,
            ):
                yield event_dict
        except Exception as e:
            yield {
                "event": "error",
                "data": json.dumps({"code": "internal", "message": str(e)[:200]}),
            }
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return EventSourceResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
        },
    )


@app.get("/api/chat/sessions")
async def api_chat_sessions(user: dict = Depends(current_user)):
    conn = db()
    sessions = chat_module.list_sessions(conn, user["uid"])
    conn.close()
    return {"ok": True, "sessions": sessions}


@app.get("/api/chat/sessions/{session_id}")
async def api_chat_session_history(session_id: str, user: dict = Depends(current_user)):
    conn = db()
    msgs = chat_module.get_session_history(conn, session_id, user["uid"], limit=200)
    conn.close()
    return {"ok": True, "messages": msgs}


# ────────── 公开接口(无需登录) ──────────

@app.post("/api/waitlist")
async def waitlist(
    contact: str = Form(...),
    channel: str = Form(default=""),
    reason: str = Form(default=""),
    request: Request = None,
):
    """早鸟等待列表 · 收集邮箱 / 手机号 / Telegram"""
    contact = contact.strip()[:200]
    if not contact:
        return JSONResponse({"ok": False, "error": "联系方式不能为空"}, 400)
    conn = db()
    conn.execute(
        "INSERT INTO waitlist (contact, channel, reason, created_at, user_agent) VALUES (?, ?, ?, ?, ?)",
        (contact, channel[:50], reason[:500], int(time.time()),
         (request.headers.get("user-agent", "")[:200]) if request else "")
    )
    conn.commit()
    count = conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    conn.close()
    return JSONResponse({"ok": True, "position": count, "message": f"已收到 · 你是第 {count} 位早鸟"})


@app.post("/api/ingest")
async def api_ingest(
    url: str = Form(...),
    request: Request = None,
    user: dict = Depends(current_user),
):
    """投喂入口 · 抓任意 URL → AI 写卡 → 进 vault · 需登录"""
    if ingest_url is None:
        return JSONResponse({"ok": False, "error": f"投喂模块加载失败: {_INGEST_IMPORT_ERROR}"}, 500)
    url = (url or "").strip()
    if not url:
        return JSONResponse({"ok": False, "error": "URL 不能为空"}, 400)
    try:
        # v1 multi-tenant: ingest_url now requires uid
        result = ingest_url(url, uid=user["uid"])
        return JSONResponse({
            "ok": True,
            "slug": result["slug"],
            "title": result["title"],
            "platform": result["platform"],
            "share_url": f"{BASE_URL}/c/{result['slug']}",
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)[:300]}, 500)


@app.get("/api/cards", response_class=JSONResponse)
async def list_cards(
    page: int = 1, size: int = 20, tag: str = "", q: str = "",
    user: dict = Depends(current_user),
):
    """列 vault 卡片(分页 · 可按 tag / 关键词过滤)· APP 端拉列表用 · 需登录"""
    vault = get_user_vault(user["uid"])
    cards = []
    for p in vault.rglob("*.md"):
        try:
            st = p.stat()
            if st.st_size < 50:
                continue
            cards.append((p, st))
        except FileNotFoundError:
            continue
    # 按 mtime 降序
    cards.sort(key=lambda x: x[1].st_mtime, reverse=True)

    results = []
    q_lower = q.lower().strip()
    for p, st in cards:
        try:
            post = frontmatter.load(p)
            title = post.metadata.get("title", p.stem)
            tags = post.metadata.get("tags", []) or []
            if isinstance(tags, str):
                tags = [tags]
            date = str(post.metadata.get("date", ""))
            summary = (post.metadata.get("solution-summary") or post.metadata.get("description") or "")[:200]
            slug = p.stem

            # tag 过滤
            if tag and tag not in [str(t) for t in tags]:
                continue
            # 关键词过滤(title / summary / content 头 500 字)
            if q_lower:
                hay = f"{title} {summary} {post.content[:500]}".lower()
                if q_lower not in hay:
                    continue

            results.append({
                "slug": slug,
                "title": title,
                "date": date,
                "tags": [str(t) for t in tags],
                "summary": summary,
                "result_chip": post.metadata.get("result_chip"),
                "size_bytes": st.st_size,
                "mtime": int(st.st_mtime),
                "share_url": f"{BASE_URL}/c/{slug}",
            })
        except Exception:
            continue

    total = len(results)
    start = (page - 1) * size
    paged = results[start:start + size]
    return {
        "total": total,
        "page": page,
        "size": size,
        "cards": paged,
    }


@app.get("/api/cards/index", response_class=JSONResponse)
async def cards_index(limit: int = 500, user: dict = Depends(current_user)):
    """L1 索引 · 轻量 · 仅 slug+description+tags+mtime+result_chip · APP Today 屏 + LLM 召回用"""
    vault = get_user_vault(user["uid"])
    items = []
    for p in vault.rglob("*.md"):
        try:
            st = p.stat()
            if st.st_size < 50:
                continue
        except FileNotFoundError:
            continue
        try:
            post = frontmatter.load(p)
        except Exception:
            continue
        meta = post.metadata
        desc = meta.get("description") or meta.get("solution-summary")
        if not desc:
            desc = post.content.strip()[:80]
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        items.append({
            "slug": p.stem,
            "description": str(desc)[:200],
            "tags": [str(t) for t in tags],
            "mtime": int(st.st_mtime),
            "result_chip": meta.get("result_chip"),
        })
        if len(items) >= max(1, min(limit, 2000)):
            break
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"items": items, "count": len(items)}


@app.get("/api/cards/{slug}", response_class=JSONResponse)
async def get_card(slug: str, user: dict = Depends(current_user)):
    """单卡 JSON · APP 端拉详情用 · 需登录 · 只在该用户自己的 vault 里找"""
    path = find_card_file(user["uid"], slug)
    if not path:
        raise HTTPException(404, "Card not found")
    try:
        post = frontmatter.load(path)
    except Exception:
        raise HTTPException(500, "Card parse failed")

    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc", "nl2br"])
    body_html = md.convert(post.content)

    return {
        "slug": slug,
        "title": post.metadata.get("title", slug),
        "date": str(post.metadata.get("date", "")),
        "tags": [str(t) for t in (post.metadata.get("tags") or [])],
        "frontmatter": {k: (str(v) if not isinstance(v, (list, dict, int, float, bool, type(None))) else v)
                        for k, v in post.metadata.items()},
        "content": post.content,
        "html": body_html,
        "share_url": f"{BASE_URL}/c/{slug}",
    }


@app.get("/api/activity", response_class=JSONResponse)
async def get_activity(limit: int = 20, user: dict = Depends(current_user)):
    """care-agent audit log · APP 端"主动关心日志"页用 · 需登录 · 仅本用户记录"""
    conn = db()
    if _table_exists(conn, "care_audit"):
        # care_audit 表如果没有 user_id 列就视作单租户旧数据(仅 uid=1 可见),
        # 加列后(Phase 1 migration)按 user_id 过滤。
        has_uid = bool(conn.execute(
            "SELECT 1 FROM pragma_table_info('care_audit') WHERE name='user_id'"
        ).fetchone())
        if has_uid:
            rows = conn.execute(
                "SELECT id, fired_at, reasoning, should_engage, message, actions, "
                "next_trigger_at, next_context FROM care_audit "
                "WHERE user_id = ? "
                "ORDER BY fired_at DESC LIMIT ?",
                (user["uid"], max(1, min(limit, 100)))
            ).fetchall()
        elif user["uid"] == 1:
            # legacy data without user_id — only owner (uid=1) sees it
            rows = conn.execute(
                "SELECT id, fired_at, reasoning, should_engage, message, actions, "
                "next_trigger_at, next_context FROM care_audit "
                "ORDER BY fired_at DESC LIMIT ?",
                (max(1, min(limit, 100)),)
            ).fetchall()
        else:
            rows = []
    else:
        rows = []
    conn.close()

    items = []
    for r in rows:
        items.append({
            "id": r["id"],
            "fired_at": r["fired_at"],
            "reasoning": r["reasoning"],
            "should_engage": bool(r["should_engage"]),
            "message": r["message"],
            "actions": r["actions"],
            "next_trigger_at": r["next_trigger_at"],
            "next_context": r["next_context"],
        })
    return {"items": items, "count": len(items)}


# REPORTS_DIR was the global single-tenant reports folder.
# In v1 it is per-user: get_user_reports(uid). Kept for migration scripts only.
_WEEK_RE = re.compile(r"^(\d{4}-W\d{2})")
_REPORT_FILENAME_RE = re.compile(r"^[\w\-\.]+\.md$")


def _report_title(path: Path) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 30:
                    break
                m = re.match(r"^#\s+(.+?)\s*$", line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return path.stem


@app.get("/api/reports", response_class=JSONResponse)
async def list_reports(limit: int = 20, user: dict = Depends(current_user)):
    """周报列表 · `_reports/*.md` 按 mtime 降序 · APP Reports 屏用 · 需登录"""
    reports_dir = get_user_reports(user["uid"])
    if not reports_dir.exists():
        return {"items": [], "count": 0}
    files = []
    for p in reports_dir.rglob("*.md"):
        try:
            st = p.stat()
            files.append((p, st))
        except FileNotFoundError:
            continue
    files.sort(key=lambda x: x[1].st_mtime, reverse=True)
    items = []
    for p, st in files[:max(1, min(limit, 100))]:
        m = _WEEK_RE.match(p.name)
        items.append({
            "filename": p.name,
            "week": m.group(1) if m else None,
            "title": _report_title(p),
            "mtime": int(st.st_mtime),
            "size_bytes": st.st_size,
        })
    return {"items": items, "count": len(items)}


@app.get("/api/reports/{filename}", response_class=JSONResponse)
async def get_report(filename: str, user: dict = Depends(current_user)):
    """单份周报 · markdown + 渲染 html · 路径穿越双重防御 · 需登录"""
    if "/" in filename or ".." in filename or not _REPORT_FILENAME_RE.match(filename):
        raise HTTPException(400, "Invalid filename")
    reports_dir = get_user_reports(user["uid"])
    path = (reports_dir / filename).resolve()
    try:
        if not path.is_relative_to(reports_dir.resolve()):
            raise HTTPException(400, "Path traversal denied")
    except AttributeError:
        # Python < 3.9 fallback
        if not str(path).startswith(str(reports_dir.resolve())):
            raise HTTPException(400, "Path traversal denied")
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Report not found")
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        raise HTTPException(500, "Report read failed")
    md = markdown.Markdown(extensions=["fenced_code", "tables", "toc", "nl2br"])
    html = md.convert(content)
    st = path.stat()
    return {
        "filename": filename,
        "title": _report_title(path),
        "content": content,
        "html": html,
        "mtime": int(st.st_mtime),
        "size_bytes": st.st_size,
    }


@app.get("/api/search", response_class=JSONResponse)
async def search_vault(q: str, limit: int = 20, user: dict = Depends(current_user)):
    """vault 全文搜索 · 返回命中卡片列表 · 需登录"""
    q = q.strip()
    if not q or len(q) < 2:
        return {"results": [], "query": q, "count": 0}

    vault = get_user_vault(user["uid"])
    q_lower = q.lower()
    hits = []
    for p in vault.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            if q_lower in text.lower():
                # 找上下文
                idx = text.lower().find(q_lower)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(q) + 100)
                snippet = "..." + text[start:end].replace("\n", " ") + "..."

                try:
                    post = frontmatter.load(p)
                    title = post.metadata.get("title", p.stem)
                except Exception:
                    title = p.stem

                hits.append({
                    "slug": p.stem,
                    "title": title,
                    "snippet": snippet,
                    "share_url": f"{BASE_URL}/c/{p.stem}",
                })
                if len(hits) >= limit:
                    break
        except Exception:
            continue
    return {"results": hits, "query": q, "count": len(hits)}


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


@app.get("/api/stats", response_class=JSONResponse)
async def stats():
    """Public anonymized aggregate. Used by /welcome marketing page only."""
    card_count = 0
    vault_size_mb = 0.0
    for _uid, _vault in iter_user_dirs():
        for f in _vault.rglob("*.md"):
            try:
                card_count += 1
                vault_size_mb += f.stat().st_size / 1024 / 1024
            except FileNotFoundError:
                continue
    vault_size_mb = round(vault_size_mb, 2)
    conn = db()
    waitlist_count = conn.execute("SELECT COUNT(*) FROM waitlist").fetchone()[0]
    user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return {
        "cards": card_count,
        "vault_mb": vault_size_mb,
        "users": user_count,
        "waitlist": waitlist_count,
        "version": "0.7.0-saas-v1",
    }


# ────────── 主页 HTML(独立 · 视觉 ≥ Apple Notes / Things 3)──────────

HOME_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>sift · AI 帮你沉淀每一段思考</title>
<meta property="og:title" content="sift · AI 知识库" />
<meta property="og:description" content="跟 AI 聊完不再消失 · AI 帮你自动写卡 · 每天主动关心" />
<meta property="og:url" content="https://sift.echovale.online" />
<!-- iOS PWA standalone(加主屏幕后全屏 · 没 Safari 工具栏)-->
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="apple-mobile-web-app-title" content="Sift" />
<meta name="format-detection" content="telephone=no" />
<meta name="theme-color" content="#F7F4EE" />
<link rel="apple-touch-icon" href="/apple-touch-icon.svg" />
<link rel="manifest" href="/manifest.json" />
<style>
  :root {{
    --bg: #F7F4EE;
    --surface: #FFFFFF;
    --surface-2: #F1EBDE;
    --ink: #1B1614;
    --ink-2: #5C544D;
    --ink-3: #908378;
    --accent: #2E5BFF;
    --warm: #D9783A;
    --border: rgba(27,22,20,.10);
    --shadow-card: 0 0.5px 0 0 rgba(255,255,255,.6) inset,
                   0 1px 2px rgba(27,22,20,.04),
                   0 4px 12px rgba(27,22,20,.04);
    --shadow-hero: 0 0.5px 0 0 rgba(255,255,255,.5) inset,
                   0 8px 24px rgba(27,22,20,.10),
                   0 32px 64px rgba(27,22,20,.14);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #15120F; --surface: #1F1A16; --surface-2: #2A231D;
      --ink: #F4EFE5; --ink-2: #B5AB9B; --ink-3: #877E70;
      --accent: #5F82FF; --warm: #E89A6A;
      --border: rgba(244,239,229,.10);
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Noto Sans SC", sans-serif;
    line-height: 1.6; -webkit-font-smoothing: antialiased;
  }}
  .hero {{
    padding: 80px 24px 64px; text-align: center; max-width: 720px; margin: 0 auto;
  }}
  .logo {{ font-size: 56px; margin-bottom: 12px; }}
  .brand-name {{ font-size: 22px; font-weight: 700; letter-spacing: 0.04em; color: var(--ink); margin-bottom: 32px; }}
  h1 {{
    font-size: 48px; font-weight: 700; line-height: 1.1;
    letter-spacing: -0.035em; margin: 0 0 16px;
  }}
  .accent {{ color: var(--accent); }}
  .warm {{ color: var(--warm); }}
  .sub {{
    font-size: 18px; color: var(--ink-2); margin: 0 auto 40px; max-width: 540px;
  }}
  .cta-row {{
    display: flex; gap: 12px; justify-content: center; flex-wrap: wrap; margin-bottom: 16px;
  }}
  .btn {{
    display: inline-block; padding: 14px 28px; border-radius: 999px;
    font-weight: 600; text-decoration: none; font-size: 16px;
    transition: transform .14s cubic-bezier(.32,.72,0,1);
  }}
  .btn:hover {{ transform: translateY(-1px); }}
  .btn-primary {{ background: var(--accent); color: white; }}
  .btn-ghost {{ background: var(--surface); color: var(--ink); border: 1px solid var(--border); }}
  .stats {{ color: var(--ink-3); font-size: 13px; margin-top: 8px; }}

  section {{ max-width: 880px; margin: 0 auto; padding: 48px 24px; }}
  .features {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 16px; margin-top: 24px;
  }}
  .card {{
    background: var(--surface); border-radius: 16px; padding: 24px;
    box-shadow: var(--shadow-card);
  }}
  .card-icon {{ font-size: 32px; margin-bottom: 8px; }}
  .card-title {{ font-weight: 600; font-size: 17px; margin-bottom: 4px; }}
  .card-desc {{ color: var(--ink-2); font-size: 14px; line-height: 1.6; }}

  h2 {{
    font-size: 32px; font-weight: 700; letter-spacing: -0.018em;
    text-align: center; margin: 0 0 24px;
  }}
  .lead {{ text-align: center; color: var(--ink-2); max-width: 540px; margin: 0 auto 32px; }}

  .compare {{
    background: var(--surface); border-radius: 22px; padding: 32px;
    box-shadow: var(--shadow-card); margin-top: 24px;
  }}
  .compare-row {{ display: grid; grid-template-columns: 1fr auto 1fr; gap: 16px; padding: 12px 0; border-bottom: 1px solid var(--border); align-items: center; }}
  .compare-row:last-child {{ border-bottom: none; }}
  .compare-row .label {{ text-align: center; color: var(--ink-3); font-size: 12px; }}
  .compare-row .col {{ font-size: 14px; }}
  .compare-row .left {{ text-align: right; color: var(--ink-3); }}
  .compare-row .right {{ color: var(--ink); }}
  .compare-row.head {{ font-weight: 700; color: var(--ink); }}
  .compare-row.head .left {{ color: var(--ink-3); }}
  .compare-row.head .right {{ color: var(--accent); }}

  .waitlist-form {{
    max-width: 480px; margin: 24px auto 0;
    background: var(--surface); border-radius: 22px; padding: 32px;
    box-shadow: var(--shadow-hero); text-align: left;
  }}
  .waitlist-form label {{ display: block; font-size: 13px; color: var(--ink-2); margin-bottom: 6px; }}
  .waitlist-form input, .waitlist-form textarea, .waitlist-form select {{
    width: 100%; padding: 12px 16px; border-radius: 12px;
    border: 1px solid var(--border); background: var(--bg); color: var(--ink);
    font-size: 15px; font-family: inherit; margin-bottom: 16px;
  }}
  .waitlist-form button {{
    width: 100%; padding: 14px; background: var(--accent); color: white;
    border: none; border-radius: 999px; font-size: 16px; font-weight: 600;
    cursor: pointer; transition: transform .14s;
  }}
  .waitlist-form button:hover {{ transform: translateY(-1px); }}
  .waitlist-msg {{ margin-top: 12px; text-align: center; font-size: 14px; color: var(--accent); }}

  .try-form {{
    max-width: 640px; margin: 24px auto 0;
    background: var(--surface); border-radius: 22px; padding: 24px;
    box-shadow: var(--shadow-hero);
    display: flex; flex-direction: column; gap: 12px;
  }}
  .try-form input {{
    padding: 14px 18px; border-radius: 12px;
    border: 1px solid var(--border); background: var(--bg); color: var(--ink);
    font-size: 15px; font-family: inherit;
  }}
  .try-form button {{
    padding: 14px; background: var(--accent); color: white;
    border: none; border-radius: 999px; font-size: 16px; font-weight: 600;
    cursor: pointer; transition: transform .14s;
  }}
  .try-form button:hover {{ transform: translateY(-1px); }}
  .try-form button:disabled {{ background: var(--ink-3); cursor: progress; }}
  .try-msg {{ text-align: center; font-size: 14px; color: var(--accent); min-height: 20px; }}
  .try-msg.err {{ color: var(--warm); }}
  .try-hints {{ font-size: 13px; color: var(--ink-3); text-align: center; }}
  .try-hints a {{ color: var(--accent); text-decoration: none; }}
  .try-hints a:hover {{ text-decoration: underline; }}

  footer {{ padding: 48px 24px; text-align: center; color: var(--ink-3); font-size: 13px; }}
  footer a {{ color: var(--ink-2); text-decoration: none; }}
  footer a:hover {{ color: var(--accent); }}
</style>
</head>
<body>
  <div class="hero">
    <div class="logo">📚</div>
    <div class="brand-name">SIFT</div>
    <h1>跟 AI 聊完<br/><span class="accent">不再消失</span></h1>
    <p class="sub">
      AI 帮你自动写卡 · 每天主动关心 · 数据完全你的<br/>
      支持自部署 + SaaS 双轨 · 跟 Notion / 豆包都不一样
    </p>
    <div class="cta-row">
      <a href="#waitlist" class="btn btn-primary">免费早鸟 · 抢席位</a>
      <a href="https://github.com/HuanNan520/sift" target="_blank" class="btn btn-ghost">GitHub 开源版 →</a>
    </div>
    <div class="stats">
      🟢 alpha 运行中 · {card_count} 张卡片 · {vault_size_mb}MB vault
    </div>
  </div>

  <section id="try-now" style="padding-top:24px;">
    <h2>现在就试一个</h2>
    <p class="lead">丢任何链接进去 · 30 秒变成你的知识卡 · 不用注册</p>
    <form class="try-form" onsubmit="submitIngest(event)">
      <input name="url" type="url" required placeholder="粘贴 B 站 / 抖音 / 微信文章 / 知乎 / 任意网页链接" />
      <button type="submit">投喂 · AI 写卡</button>
      <div class="try-msg" id="try-msg"></div>
      <div class="try-hints">
        💡 例:
        <a href="#" onclick="fillTry('https://mp.weixin.qq.com/s/iX23Df_KQCEjFCx0n9LMyA');return false;">微信文章</a> ·
        <a href="#" onclick="fillTry('https://www.zhihu.com/question/30957534');return false;">知乎</a> ·
        <a href="#" onclick="fillTry('https://www.bilibili.com/video/BV1uv411q7Mv');return false;">B 站视频</a>
      </div>
    </form>
  </section>

  <section>
    <h2>这不是又一个豆包</h2>
    <p class="lead">所有 AI 聊天产品都让你聊完就忘 · sift 让 AI 记住你</p>
    <div class="features">
      <div class="card">
        <div class="card-icon">✍️</div>
        <div class="card-title">AI 自动写卡</div>
        <div class="card-desc">跟 Claude / ChatGPT 聊完 · sift 后台判断要不要沉淀 · 自动写 markdown 卡片进你 vault</div>
      </div>
      <div class="card">
        <div class="card-icon">💗</div>
        <div class="card-title">AI 主动关心</div>
        <div class="card-desc">不是早晚问安 · AI 看你 vault + 状态 · 自己决定何时关心 · 像家人不是机器人</div>
      </div>
      <div class="card">
        <div class="card-icon">🎬</div>
        <div class="card-title">投喂任何链接</div>
        <div class="card-desc">B 站 / 抖音 / 微信文章 / 知乎 / 任意网页 · 丢一个链接给 sift · AI 写卡 + 关联你历史</div>
      </div>
      <div class="card">
        <div class="card-icon">🔗</div>
        <div class="card-title">卡片分享 URL</div>
        <div class="card-desc">把整理好的卡发给朋友 · 浏览器直接看 · 不需要 sift 账号</div>
      </div>
      <div class="card">
        <div class="card-icon">📦</div>
        <div class="card-title">vault 完全你的</div>
        <div class="card-desc">markdown 文件 · 随时一键导出 · 自托管开源版也行 · 不绑架你</div>
      </div>
      <div class="card">
        <div class="card-icon">🎯</div>
        <div class="card-title">一句话调动历史</div>
        <div class="card-desc">"把我上个月研究的护理资料整合成 PPT 大纲" · AI 从你 vault 召回 + 整合</div>
      </div>
    </div>
  </section>

  <section>
    <h2>跟其他 AI 怎么不一样</h2>
    <div class="compare">
      <div class="compare-row head">
        <div class="col left">豆包 / Kimi / ChatGPT</div>
        <div class="label"> </div>
        <div class="col right">sift</div>
      </div>
      <div class="compare-row">
        <div class="col left">聊完啥都没留下</div>
        <div class="label">↔</div>
        <div class="col right">AI 自动写卡进 vault</div>
      </div>
      <div class="compare-row">
        <div class="col left">每次重新开始</div>
        <div class="label">↔</div>
        <div class="col right">AI 1 年下来真懂你</div>
      </div>
      <div class="compare-row">
        <div class="col left">数据锁在平台</div>
        <div class="label">↔</div>
        <div class="col right">markdown 完全你的</div>
      </div>
      <div class="compare-row">
        <div class="col left">主动 = 早晚问安</div>
        <div class="label">↔</div>
        <div class="col right">AI 看状态自己决定何时关心</div>
      </div>
      <div class="compare-row">
        <div class="col left">投喂只支持纯文本</div>
        <div class="label">↔</div>
        <div class="col right">B 站 / 抖音 / 微信任意</div>
      </div>
      <div class="compare-row">
        <div class="col left">不开源 / 不能自部署</div>
        <div class="label">↔</div>
        <div class="col right">AGPL 开源 + SaaS 双轨</div>
      </div>
    </div>
  </section>

  <section id="waitlist">
    <h2>早鸟通道</h2>
    <p class="lead">现在是 alpha 阶段 · 限量内测 · 留个联系方式我邀你</p>
    <form class="waitlist-form" onsubmit="submitWaitlist(event)">
      <label>联系方式 *(邮箱 / 手机号 / Telegram @handle)</label>
      <input name="contact" required placeholder="比如 you@example.com 或 +86 138 0000 0000" />

      <label>你在哪个领域?(让我帮你匹配 vault 模板)</label>
      <select name="channel">
        <option value="">选一个最贴近的</option>
        <option value="护理医疗">护理 / 医疗</option>
        <option value="法律金融">法律 / 金融</option>
        <option value="开发者">开发者 / 极客</option>
        <option value="学生">学生 / 备考</option>
        <option value="自由职业">自由职业 / 创作者</option>
        <option value="技工">技工 / 修车工</option>
        <option value="其他">其他</option>
      </select>

      <label>一句话告诉我你为啥想用 sift?(可选)</label>
      <textarea name="reason" rows="2" placeholder="比如:跟 ChatGPT 聊完总是丢"></textarea>

      <button type="submit">免费抢席位</button>
      <div class="waitlist-msg" id="waitlist-msg"></div>
    </form>
  </section>

  <footer>
    <p>
      <a href="https://github.com/HuanNan520/sift" target="_blank">GitHub 开源版</a> ·
      <a href="https://huannan.top" target="_blank">作者博客</a> ·
      <a href="mailto:3270842397@qq.com">联系</a>
    </p>
    <p style="margin-top: 16px; font-size: 12px;">
      sift v0.2.0-alpha · 飞牛 NAS 跑着 · 数据完全你的
    </p>
  </footer>

  <script>
    function fillTry(url) {{
      document.querySelector('.try-form input[name="url"]').value = url;
    }}

    async function submitIngest(e) {{
      e.preventDefault();
      const form = e.target;
      const btn = form.querySelector('button');
      const msg = document.getElementById('try-msg');
      btn.disabled = true;
      btn.textContent = 'AI 正在写卡 · 30 秒...';
      msg.className = 'try-msg';
      msg.textContent = '';
      const fd = new FormData(form);
      try {{
        const r = await fetch('/api/ingest', {{ method: 'POST', body: fd }});
        const d = await r.json();
        if (d.ok) {{
          msg.innerHTML = '✅ 已沉淀!<a href="' + d.share_url + '" target="_blank" style="margin-left:12px;text-decoration:underline;">看卡 →</a>';
          form.reset();
          // 自动打开
          window.open(d.share_url, '_blank');
        }} else {{
          msg.className = 'try-msg err';
          msg.textContent = '❌ ' + (d.error || '出错了');
        }}
      }} catch (err) {{
        msg.className = 'try-msg err';
        msg.textContent = '❌ 网络错了 · 试试再来';
      }}
      btn.disabled = false;
      btn.textContent = '投喂 · AI 写卡';
    }}

    async function submitWaitlist(e) {{
      e.preventDefault();
      const form = e.target;
      const btn = form.querySelector('button');
      const msg = document.getElementById('waitlist-msg');
      btn.disabled = true;
      btn.textContent = '提交中...';
      const fd = new FormData(form);
      try {{
        const r = await fetch('/api/waitlist', {{ method: 'POST', body: fd }});
        const d = await r.json();
        if (d.ok) {{
          msg.textContent = d.message || '已收到!';
          form.reset();
        }} else {{
          msg.textContent = d.error || '出错了 · 试试再来';
        }}
      }} catch (err) {{
        msg.textContent = '网络错了 · 试试再来';
      }}
      btn.disabled = false;
      btn.textContent = '免费抢席位';
    }}
  </script>
</body>
</html>
"""


# ────────── v0.6 路由重排:landing / download / PWA / 静态资源 ─────
# 顺序:
#   1. 显式 @app.get("/") → landing.html (产品体验页)
#   2. @app.get("/welcome") → landing alias (B 站简介旧链接兼容)
#   3. @app.get("/download") → download.html (装机引导)
#   4. mount /app → PWA SPA (新装的客户端 + 用 /app/ 入口)
#   5. mount / → 静态资源 fallback (旧 PWA 用户从 / 装机用到的 .css .js .sw.js)
#
# FastAPI 规则:@app.get 装饰路由优先于 mount · mount 之间按注册顺序
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PWA_DIR = os.environ.get("SIFT_PWA_DIR", "/vol1/1000/sift/pwa")
LANDING_PATH = Path(PWA_DIR) / "landing.html"
DOWNLOAD_PATH = Path(PWA_DIR) / "download.html"


@app.get("/", response_class=HTMLResponse)
async def landing_root():
    """主页 = 产品 landing 页 · funnel 顶端"""
    if LANDING_PATH.exists():
        return HTMLResponse(LANDING_PATH.read_text(encoding="utf-8"))
    # fallback to old HOME_HTML(实际不会走到 · landing.html 应存在)
    card_count = 0
    vault_size_mb = 0.0
    for _uid, _vault in iter_user_dirs():
        for f in _vault.rglob("*.md"):
            try:
                card_count += 1
                vault_size_mb += f.stat().st_size / 1024 / 1024
            except FileNotFoundError:
                continue
    return HOME_HTML.format(card_count=card_count, vault_size_mb=int(vault_size_mb))


@app.get("/download", response_class=HTMLResponse)
async def download_page():
    """装机引导 · iOS PWA + Android APK + 桌面 PWA"""
    if DOWNLOAD_PATH.exists():
        return HTMLResponse(DOWNLOAD_PATH.read_text(encoding="utf-8"))
    raise HTTPException(404, "download page not deployed")


PRIVACY_PATH = Path(PWA_DIR) / "sift-privacy.html"


@app.get("/sift-privacy", response_class=HTMLResponse)
@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page():
    """隐私政策 · Google Play / App Store / Microsoft Store 上架要求"""
    if PRIVACY_PATH.exists():
        return HTMLResponse(PRIVACY_PATH.read_text(encoding="utf-8"))
    raise HTTPException(404, "privacy page not deployed")


# /app → /app/(避免末尾斜杠 404)
@app.get("/app", include_in_schema=False)
async def app_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/app/", status_code=302)


if Path(PWA_DIR).exists():
    # 新 PWA 入口:/app/* 走 SPA
    app.mount("/app", StaticFiles(directory=PWA_DIR, html=True), name="pwa_app")
    # 静态资源 fallback / · 旧 PWA 用户 start_url=/ 装的 SW 引用相对路径
    # html=False 让 / 直接路由(landing) 不被 index.html 覆盖
    app.mount("/", StaticFiles(directory=PWA_DIR, html=False), name="pwa_legacy")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
