"""
sift retriever · vault-aware 检索给 chat 用

设计:
  - jieba 中文切分 + 简化 BM25 内存索引
  - 启动时一次性扫 vault → 切分 → 倒排表
  - search(uid, query, top_k=6) → 返 [{slug, title, score, snippet, tags}]
  - 加卡时调 invalidate_index() 让下次 search 重建
  - 353 张卡建索引 < 3 秒 · 不上 SQLite FTS5 减少复杂度

后续扩展:
  - cards 表 + FTS5 (10000+ 卡再上)
  - 向量 embedding (要召回偏义近词时再上)
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import frontmatter

# jieba 启动慢 · 第一次 cut 会建词典 · 但只一次
import jieba

# 关闭 jieba 详细日志
jieba.setLogLevel(20)

# ────────── 内存索引 ──────────

_lock = threading.RLock()
_INDEX = {
    "built_at": 0.0,
    "vault_root": None,
    "docs": [],          # [{slug, title, tags, summary, content, mtime}]
    "tf": [],            # [Counter, ...] 跟 docs index 对齐
    "df": Counter(),     # term → doc 频次
    "doc_len": [],       # [int, ...]
    "avg_doc_len": 1.0,
    "N": 0,
}

_INDEX_TTL_SEC = 300       # 5 分钟外重新扫(简化版避免 inotify)
_MAX_CONTENT_FOR_INDEX = 6000  # 单卡只索引头 6000 字 · 节省内存


def _tokenize(text: str) -> list[str]:
    """jieba 搜索模式切分 + 归一 · 含中英文"""
    if not text:
        return []
    text = text.lower()
    tokens = jieba.cut_for_search(text)
    out = []
    for t in tokens:
        t = t.strip()
        if len(t) >= 1 and not t.isspace():
            out.append(t)
    return out


def _load_card(md_path: Path) -> Optional[dict]:
    """读 markdown + frontmatter · 返 None 跳过"""
    try:
        st = md_path.stat()
        if st.st_size < 50:
            return None
        post = frontmatter.load(md_path)
        slug = md_path.stem
        title = str(post.metadata.get("title", slug))
        tags_raw = post.metadata.get("tags", []) or []
        if isinstance(tags_raw, str):
            tags_raw = [tags_raw]
        tags = [str(t) for t in tags_raw]
        summary = str(
            post.metadata.get("solution-summary")
            or post.metadata.get("description")
            or ""
        )[:300]
        content = post.content[:_MAX_CONTENT_FOR_INDEX]
        return {
            "slug": slug,
            "title": title,
            "tags": tags,
            "summary": summary,
            "content": content,
            "mtime": int(st.st_mtime),
            "path": str(md_path),
        }
    except Exception:
        return None


def build_index(vault_root: str | Path, force: bool = False) -> dict:
    """全量扫 vault 建索引 · 加锁防并发"""
    vault_root = Path(vault_root)
    with _lock:
        if (
            not force
            and _INDEX["vault_root"] == str(vault_root)
            and (time.time() - _INDEX["built_at"]) < _INDEX_TTL_SEC
            and _INDEX["docs"]
        ):
            return _INDEX

        docs: list[dict] = []
        tf_list: list[Counter] = []
        doc_len: list[int] = []
        df: Counter = Counter()

        if not vault_root.exists():
            _INDEX.update({
                "built_at": time.time(),
                "vault_root": str(vault_root),
                "docs": [], "tf": [], "df": Counter(),
                "doc_len": [], "avg_doc_len": 1.0, "N": 0,
            })
            return _INDEX

        for md in vault_root.rglob("*.md"):
            card = _load_card(md)
            if not card:
                continue
            full_text = f"{card['title']}\n{' '.join(card['tags'])}\n{card['summary']}\n{card['content']}"
            tokens = _tokenize(full_text)
            if not tokens:
                continue
            tf = Counter(tokens)
            docs.append(card)
            tf_list.append(tf)
            doc_len.append(len(tokens))
            for term in set(tokens):
                df[term] += 1

        N = len(docs)
        avg = (sum(doc_len) / N) if N else 1.0

        _INDEX.update({
            "built_at": time.time(),
            "vault_root": str(vault_root),
            "docs": docs,
            "tf": tf_list,
            "df": df,
            "doc_len": doc_len,
            "avg_doc_len": avg,
            "N": N,
        })
        return _INDEX


def invalidate_index() -> None:
    """让下次 search/build 强制重建 · ingest 写新卡后调"""
    with _lock:
        _INDEX["built_at"] = 0.0


def ensure_built(vault_root: str | Path) -> None:
    """search 前调 · 索引旧就重建"""
    if _INDEX["vault_root"] != str(vault_root) or (time.time() - _INDEX["built_at"]) > _INDEX_TTL_SEC:
        build_index(vault_root, force=True)


def search(
    vault_root: str | Path,
    query: str,
    top_k: int = 6,
    uid: int = 1,
) -> list[dict]:
    """BM25 检索 · 返 top-k [{slug, title, score, snippet, tags}]"""
    ensure_built(vault_root)
    with _lock:
        if _INDEX["N"] == 0:
            return []
        N = _INDEX["N"]
        avg_dl = max(_INDEX["avg_doc_len"], 1.0)
        docs = _INDEX["docs"]
        tf_list = _INDEX["tf"]
        df = _INDEX["df"]
        doc_len = _INDEX["doc_len"]

    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    k1, b = 1.5, 0.75
    scores: list[tuple[int, float]] = []
    for i in range(N):
        tf = tf_list[i]
        dl = doc_len[i]
        s = 0.0
        for q in q_tokens:
            if q not in tf:
                continue
            n_q = df.get(q, 0) or 1
            idf = math.log((N - n_q + 0.5) / (n_q + 0.5) + 1.0)
            tf_q = tf[q]
            denom = tf_q + k1 * (1 - b + b * dl / avg_dl)
            s += idf * (tf_q * (k1 + 1)) / max(denom, 1e-9)
        if s > 0:
            scores.append((i, s))

    scores.sort(key=lambda x: -x[1])
    top = scores[:top_k]
    results = []
    for i, score in top:
        d = docs[i]
        snippet = d["summary"] or d["content"][:160]
        # 优先用 query 命中位置摘要
        content_lower = d["content"].lower()
        for q in q_tokens:
            pos = content_lower.find(q)
            if pos >= 0:
                start = max(0, pos - 60)
                end = min(len(d["content"]), pos + 80)
                ctx = d["content"][start:end].replace("\n", " ").strip()
                snippet = ("…" if start > 0 else "") + ctx + ("…" if end < len(d["content"]) else "")
                break
        results.append({
            "slug": d["slug"],
            "title": d["title"],
            "tags": d["tags"],
            "score": round(score, 3),
            "snippet": snippet[:220],
            "mtime": d["mtime"],
        })
    return results


def get_card_for_context(vault_root: str | Path, slug: str) -> Optional[dict]:
    """拉单卡全文(chat 上下文拼装用)· 优先 cache · 没 cache 直接读盘"""
    ensure_built(vault_root)
    with _lock:
        for d in _INDEX["docs"]:
            if d["slug"] == slug:
                return d
    # cache 没有 → 直接读盘
    for md in Path(vault_root).rglob(f"{slug}.md"):
        return _load_card(md)
    return None


def index_stats() -> dict:
    """debug 用 · 看索引状态"""
    return {
        "vault_root": _INDEX["vault_root"],
        "built_at": _INDEX["built_at"],
        "age_sec": int(time.time() - _INDEX["built_at"]) if _INDEX["built_at"] else None,
        "N": _INDEX["N"],
        "avg_doc_len": round(_INDEX["avg_doc_len"], 1),
        "vocab_size": len(_INDEX["df"]),
    }


if __name__ == "__main__":
    # CLI 自测: python retriever.py "sift PWA"
    import sys
    import json
    # CLI tester defaults to uid 1's vault under the new SIFT_USERS_ROOT layout
    _users = os.environ.get("SIFT_USERS_ROOT", "/vol1/1000/sift/users")
    vault = os.environ.get("SIFT_ROOT", f"{_users}/1/vault")
    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
        t0 = time.time()
        build_index(vault, force=True)
        print(f"index built in {time.time()-t0:.2f}s · stats: {json.dumps(index_stats(), ensure_ascii=False)}")
        t1 = time.time()
        hits = search(vault, q, top_k=6)
        print(f"search '{q}' in {(time.time()-t1)*1000:.1f}ms · {len(hits)} hits")
        for h in hits:
            print(f"  · {h['score']} {h['slug']}: {h['title'][:50]}")
            print(f"    {h['snippet'][:120]}")
