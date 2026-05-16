"""
sift auth · argon2id 密码 + JWT access(30min HS256) + opaque refresh(30d DB stored)

用法:
  from auth import (
    hash_password, verify_password,
    create_access_token, decode_access_token,
    create_refresh_token, revoke_refresh_token, rotate_refresh_token,
    current_user, current_user_optional,
    ensure_auth_schema,
  )

设计:
  - access token = JWT HS256, payload {uid, plan_id, exp, iat, type:"access"}
  - refresh token = 32 byte secrets.token_urlsafe, DB stored, 30d expire
  - 旋转: 每次 refresh 撤销旧的发新的(防被盗)
  - 密码: argon2id(time_cost=3, memory_cost=64MB, parallelism=4) — 业界推荐
"""
from __future__ import annotations

import os
import json
import time
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ────────── 配置 ──────────

JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_REFRESH_SECRET = os.environ.get("JWT_REFRESH_SECRET")  # 暂未使用 · 留位

ACCESS_TTL = timedelta(minutes=30)
REFRESH_TTL = timedelta(days=30)
JWT_ALG = "HS256"

if not JWT_SECRET:
    # 首启没配 · 用临时 random 跑(重启失效让用户重登)+ 打 warn
    import warnings
    JWT_SECRET = secrets.token_urlsafe(64)
    warnings.warn(
        "JWT_SECRET 未配置 · 使用临时 random secret · 重启后所有 token 失效 · "
        "生产请设 JWT_SECRET 环境变量(64 byte 随机 base64url)",
        RuntimeWarning,
    )

# ────────── 密码 ──────────

# argon2id 默认参数 OWASP 推荐 2025+
_PH = PasswordHasher(
    time_cost=3,         # 迭代次数
    memory_cost=65536,   # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(plain: str) -> str:
    if not plain or len(plain) < 6:
        raise ValueError("密码至少 6 字符")
    if len(plain) > 256:
        raise ValueError("密码过长(>256)")
    return _PH.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        _PH.verify(hashed, plain)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """argon2 参数升级后老 hash 是否需要重算"""
    try:
        return _PH.check_needs_rehash(hashed)
    except Exception:
        return False


# ────────── JWT access token ──────────

def create_access_token(uid: int, plan_id: int = 1, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "uid": uid,
        "plan_id": plan_id,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TTL).timestamp()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_access_token(token: str) -> dict:
    """decode 并验签 · 过期 / 无效抛 jwt.* 异常"""
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])


# ────────── refresh token(DB stored opaque) ──────────

def create_refresh_token(conn: sqlite3.Connection, uid: int, ua: str = "") -> str:
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + int(REFRESH_TTL.total_seconds())
    conn.execute(
        "INSERT INTO refresh_tokens(token, uid, ua, expires_at, created_at) "
        "VALUES(?, ?, ?, ?, ?)",
        (token, uid, (ua or "")[:200], expires_at, now),
    )
    conn.commit()
    return token


def lookup_refresh_token(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    """查 refresh token · 返 row 或 None · 自动剔除过期/撤销"""
    if not token:
        return None
    now = int(time.time())
    row = conn.execute(
        "SELECT token, uid, expires_at, revoked_at FROM refresh_tokens WHERE token=?",
        (token,),
    ).fetchone()
    if not row:
        return None
    if row["revoked_at"] is not None:
        return None
    if row["expires_at"] < now:
        return None
    return dict(row)


def revoke_refresh_token(conn: sqlite3.Connection, token: str) -> None:
    now = int(time.time())
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at=? WHERE token=? AND revoked_at IS NULL",
        (now, token),
    )
    conn.commit()


def revoke_all_refresh_tokens(conn: sqlite3.Connection, uid: int) -> None:
    """撤销该用户所有 refresh token(改密码 / 主动登出全部)"""
    now = int(time.time())
    conn.execute(
        "UPDATE refresh_tokens SET revoked_at=? WHERE uid=? AND revoked_at IS NULL",
        (now, uid),
    )
    conn.commit()


def rotate_refresh_token(conn: sqlite3.Connection, old_token: str, ua: str = "") -> Optional[tuple[int, str]]:
    """撤销旧 refresh + 发新的 · 返 (uid, new_token) · 不合法返 None"""
    row = lookup_refresh_token(conn, old_token)
    if not row:
        return None
    uid = row["uid"]
    revoke_refresh_token(conn, old_token)
    new_token = create_refresh_token(conn, uid, ua)
    return uid, new_token


# ────────── FastAPI dependencies ──────────

_bearer = HTTPBearer(auto_error=False)


async def _resolve_user_from_token(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials],
    required: bool,
) -> Optional[dict]:
    """通用 · cred 为空 + required=False 返 None · 否则 401"""
    if cred is None or cred.scheme.lower() != "bearer":
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "auth_required", "message": "需要登录"},
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None
    try:
        payload = decode_access_token(cred.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_expired", "message": "token 已过期 · 用 refresh"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "token_invalid", "message": "token 无效"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail={"error": "token_wrong_type"})
    request.state.uid = payload["uid"]
    request.state.plan_id = payload.get("plan_id", 1)
    return payload


async def current_user(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """必须登录 · payload {uid, plan_id, ...}"""
    return await _resolve_user_from_token(request, cred, required=True)


async def current_user_optional(
    request: Request,
    cred: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Optional[dict]:
    """可选登录 · 没 token 返 None(公开 endpoint 但若登录就识别用户)"""
    return await _resolve_user_from_token(request, cred, required=False)


# ────────── schema ──────────

def ensure_auth_schema(conn: sqlite3.Connection) -> None:
    """
    幂等建表 + 安全的列扩展(老 users 表已有简版 · 加缺的列)
    """
    # plans
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            price_cny INTEGER DEFAULT 0,
            quota_ingest_day INTEGER DEFAULT 1,
            quota_chat_day INTEGER DEFAULT 5,
            quota_cards_total INTEGER DEFAULT 200,
            features TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            token TEXT PRIMARY KEY,
            uid INTEGER NOT NULL,
            ua TEXT,
            created_at INTEGER NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_refresh_uid ON refresh_tokens(uid);
        CREATE INDEX IF NOT EXISTS idx_refresh_expires ON refresh_tokens(expires_at);
    """)

    # 种 free plan(id=1)
    conn.execute(
        "INSERT OR IGNORE INTO plans(id, code, name, price_cny, quota_ingest_day, "
        "quota_chat_day, quota_cards_total, features) VALUES(1, 'free', 'Free 试用', 0, 1, 5, 200, "
        "'{\"byok\": true, \"care_agent\": true, \"chat_history\": true}')"
    )

    # users 表已存在(sift-api.py init_db)· 加缺的列(SQLite ALTER TABLE 限制:一次加一列)
    existing_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    additions = [
        ("pwd_hash", "TEXT"),
        ("plan_id", "INTEGER DEFAULT 1"),
        ("plan_valid_until", "INTEGER"),  # unix ts
        ("quota_used", "TEXT DEFAULT '{}'"),  # JSON {chat_today, ingest_today, reset_at}
        ("byok_blob", "TEXT"),
        ("email_verified_at", "INTEGER"),
        ("last_login_at", "INTEGER"),
        ("verify_token", "TEXT"),           # email verification token (Phase 2)
        ("verify_token_at", "INTEGER"),     # token issue time (24h TTL)
    ]
    for col, typ in additions:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")

    # care_audit 加 user_id 列(legacy 数据 user_id 为 NULL,代码已 fallback 给 uid=1)
    if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='care_audit'").fetchone():
        audit_cols = {r["name"] for r in conn.execute("PRAGMA table_info(care_audit)")}
        if "user_id" not in audit_cols:
            conn.execute("ALTER TABLE care_audit ADD COLUMN user_id INTEGER")

    # usage_log: per-LLM-call accounting (Phase 2)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            endpoint TEXT NOT NULL,
            model TEXT,
            provider TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            estimated_cost_cny REAL DEFAULT 0.0,
            byok INTEGER DEFAULT 0,
            ts INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usage_user_ts ON usage_log(user_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_log(ts);

        CREATE TABLE IF NOT EXISTS invites (
            code TEXT PRIMARY KEY,
            generated_by INTEGER,
            generated_at INTEGER NOT NULL,
            used_by INTEGER,
            used_at INTEGER,
            note TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_invites_used ON invites(used_by);
    """)

    conn.commit()


# ────────── Email verify helpers (Phase 2) ──────────

def set_verify_token(conn: sqlite3.Connection, uid: int, token: str) -> None:
    conn.execute(
        "UPDATE users SET verify_token=?, verify_token_at=? WHERE id=?",
        (token, int(time.time()), uid),
    )
    conn.commit()


def get_user_by_verify_token(conn: sqlite3.Connection, token: str) -> Optional[dict]:
    if not token:
        return None
    row = conn.execute("SELECT * FROM users WHERE verify_token=?", (token,)).fetchone()
    return dict(row) if row else None


def mark_email_verified(conn: sqlite3.Connection, uid: int) -> None:
    conn.execute(
        "UPDATE users SET email_verified_at=?, verify_token=NULL, verify_token_at=NULL WHERE id=?",
        (int(time.time()), uid),
    )
    conn.commit()


# ────────── Usage log helpers (Phase 2) ──────────

def log_llm_usage(
    conn: sqlite3.Connection, uid: int, endpoint: str, model: str, provider: str,
    input_tokens: int, output_tokens: int, estimated_cost_cny: float, byok: bool,
) -> None:
    conn.execute(
        "INSERT INTO usage_log(user_id, endpoint, model, provider, input_tokens, "
        "output_tokens, estimated_cost_cny, byok, ts) VALUES(?,?,?,?,?,?,?,?,?)",
        (uid, endpoint, model, provider, int(input_tokens or 0), int(output_tokens or 0),
         float(estimated_cost_cny or 0.0), 1 if byok else 0, int(time.time())),
    )
    conn.commit()


def get_usage_summary(conn: sqlite3.Connection, uid: int, since_ts: int) -> dict:
    row = conn.execute(
        "SELECT COUNT(*) as n, SUM(input_tokens) as in_t, SUM(output_tokens) as out_t, "
        "SUM(estimated_cost_cny) as cost FROM usage_log WHERE user_id=? AND ts>=?",
        (uid, int(since_ts)),
    ).fetchone()
    return {
        "calls": row["n"] or 0,
        "input_tokens": row["in_t"] or 0,
        "output_tokens": row["out_t"] or 0,
        "estimated_cost_cny": round(row["cost"] or 0.0, 4),
    }


# ────────── Invite code helpers (Phase 2) ──────────

def issue_invite(conn: sqlite3.Connection, generated_by: Optional[int], note: str = "") -> str:
    """Generate a fresh invite code, persist to the invites table, return the code."""
    for _ in range(20):
        cand = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8].upper()
        if not conn.execute("SELECT 1 FROM invites WHERE code=?", (cand,)).fetchone():
            conn.execute(
                "INSERT INTO invites(code, generated_by, generated_at, note) VALUES(?,?,?,?)",
                (cand, generated_by, int(time.time()), note[:200]),
            )
            conn.commit()
            return cand
    raise RuntimeError("Could not generate unique invite code after 20 attempts")


def consume_invite(conn: sqlite3.Connection, code: str, used_by_uid: int) -> bool:
    """Mark an invite code consumed. Returns True if redeemed, False if missing/used."""
    if not code:
        return False
    code = code.strip().upper()
    row = conn.execute("SELECT used_by FROM invites WHERE code=?", (code,)).fetchone()
    if not row:
        # Allow soft-mode invites that match another user's invite_code column
        # (alpha link-sharing) — only the first such redemption is allowed.
        legacy = conn.execute("SELECT id FROM users WHERE invite_code=?", (code,)).fetchone()
        if legacy:
            return True
        return False
    if row["used_by"] is not None:
        return False
    conn.execute(
        "UPDATE invites SET used_by=?, used_at=? WHERE code=?",
        (used_by_uid, int(time.time()), code),
    )
    conn.commit()
    return True


def list_invites(conn: sqlite3.Connection, limit: int = 100) -> list:
    rows = conn.execute(
        "SELECT code, generated_by, generated_at, used_by, used_at, note "
        "FROM invites ORDER BY generated_at DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]


# ────────── 用户 CRUD helper ──────────

def get_user_by_email(conn: sqlite3.Connection, email: str) -> Optional[dict]:
    if not email:
        return None
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def get_user_by_id(conn: sqlite3.Connection, uid: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    return dict(row) if row else None


def create_user(
    conn: sqlite3.Connection,
    email: str,
    password: str,
    invite_code: Optional[str] = None,
    invited_by: Optional[str] = None,
) -> dict:
    """创建用户 · email 重复抛 ValueError"""
    email = (email or "").lower().strip()
    if not email or "@" not in email or len(email) > 200:
        raise ValueError("邮箱格式不对")
    if get_user_by_email(conn, email):
        raise ValueError("邮箱已注册")
    pwd_hash = hash_password(password)
    now = int(time.time())
    # 生成唯一 invite code · 重试 5 次
    own_invite = None
    for _ in range(5):
        cand = secrets.token_urlsafe(6).replace("_", "").replace("-", "")[:8].upper()
        if not conn.execute("SELECT 1 FROM users WHERE invite_code=?", (cand,)).fetchone():
            own_invite = cand
            break
    own_invite = own_invite or secrets.token_urlsafe(8)[:8].upper()
    cur = conn.execute(
        "INSERT INTO users(email, pwd_hash, plan_id, invite_code, invited_by, "
        "created_at, last_login_at, quota_used, tier) "
        "VALUES(?, ?, 1, ?, ?, ?, ?, '{}', 'free')",
        (email, pwd_hash, own_invite, invited_by, now, now),
    )
    conn.commit()
    return get_user_by_id(conn, cur.lastrowid)


def touch_login(conn: sqlite3.Connection, uid: int) -> None:
    conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (int(time.time()), uid))
    conn.commit()


# ────────── 配额查询(给前端用 · 真扣额在 quota.py) ──────────

def get_user_plan(conn: sqlite3.Connection, uid: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT p.* FROM plans p JOIN users u ON u.plan_id=p.id WHERE u.id=?",
        (uid,),
    ).fetchone()
    return dict(row) if row else None


def get_quota_used(conn: sqlite3.Connection, uid: int) -> dict:
    """返 {chat_today, ingest_today, reset_at}"""
    row = conn.execute("SELECT quota_used FROM users WHERE id=?", (uid,)).fetchone()
    if not row or not row["quota_used"]:
        return {"chat_today": 0, "ingest_today": 0, "reset_at": _next_reset_at()}
    try:
        data = json.loads(row["quota_used"])
    except json.JSONDecodeError:
        data = {}
    reset_at = data.get("reset_at", 0)
    if reset_at and reset_at < int(time.time()):
        # 已过 reset 时间 · 视为清零(真清零在 quota.py 写入时做)
        return {"chat_today": 0, "ingest_today": 0, "reset_at": _next_reset_at()}
    return {
        "chat_today": int(data.get("chat_today", 0)),
        "ingest_today": int(data.get("ingest_today", 0)),
        "reset_at": int(data.get("reset_at", _next_reset_at())),
    }


def _next_reset_at() -> int:
    """次日 00:00 UTC+8 的 unix ts(用户在中国 · 配额按本地日重置)"""
    now = datetime.now(timezone(timedelta(hours=8)))
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(tomorrow.timestamp())
