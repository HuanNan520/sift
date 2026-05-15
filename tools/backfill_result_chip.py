#!/usr/bin/env python3
"""
backfill_result_chip.py — 给 vault 里现有卡补 result_chip frontmatter 字段。

用法:
    python tools/backfill_result_chip.py [--apply] [--limit N] [--vault PATH]

默认 dry-run,只 print。--apply 才真写 frontmatter。
idempotent: 已有 result_chip 的卡跳过。

LLM 走 SiliconFlow,5 卡一 batch,model 用 SF_MODEL 环境变量 (默认 DeepSeek-V3)。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

# 复用 sink-agent 的 SF 配置
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from importlib import import_module
    _sa = import_module("sift-sink-agent".replace("-", "_"))  # py 不允许 - 进 module name
    load_sf_key = _sa.load_sf_key
    SF_URL = _sa.SF_URL
    SF_MODEL = _sa.SF_MODEL
except Exception:
    # fallback inline
    SF_URL = os.environ.get("LLM_API_URL", "https://api.siliconflow.cn/v1/chat/completions")
    SF_MODEL = os.environ.get("LLM_MODEL", "deepseek-ai/DeepSeek-V3")

    def load_sf_key() -> str:
        for var in ("LLM_API_KEY", "DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
            v = os.environ.get(var, "")
            if v.startswith("sk-"):
                return v
        key_path = Path.home() / ".claude/projects/-home-huannan/memory/reference_siliconflow_api.md"
        if key_path.exists():
            content = key_path.read_text(encoding="utf-8")
            m = re.search(r"\*\*Key\*\*:\s*`(sk-[^`]+)`", content)
            return m.group(1) if m else ""
        return ""

import frontmatter

VALID_CHIPS = {"盲点", "复盘", "替做", "坑提醒"}

SYSTEM_PROMPT = """你给 sift APP 的卡片打"结果标签"。读下面 5 张卡的标题 + 内容片段,
判断每张该挂哪种 result_chip(用户在 APP Today/Vault 屏上看到的标签):

- "盲点"   = 卡片帮用户指出他没想到的点 / 上次没注意 / 发现的漏洞
- "复盘"   = 卡片整理过去事件 / 旧案 / 历史方案 / 跨案关联
- "替做"   = sift 替用户做了某件事 (自动整理周报 / 生成 PPT / 自动归档 / 跨设备同步推送)
- "坑提醒" = 已经否过的方案 / 已知失败路径 / 别再重复犯错
- null    = 不属于以上 4 类

输出严格 JSON,无 markdown 包裹:
[
  {"slug": "xxx", "result_chip": "盲点"},
  {"slug": "yyy", "result_chip": null},
  ...
]

注意:
- 一张卡只能一个 chip 或 null,不能多个
- 不确定就 null,不要强凑
- 大多数 debug/research/scripts 卡其实是 null,只有真符合上面 4 类的才打"""


def call_llm_batch(cards: list, timeout: int = 120) -> dict | None:
    """call SF,返 {slug: chip_or_null} dict"""
    key = load_sf_key()
    if not key:
        print("ERROR: no SiliconFlow API key", file=sys.stderr)
        return None
    user_msg = json.dumps([
        {"slug": c["slug"], "title": c["title"], "snippet": c["snippet"]}
        for c in cards
    ], ensure_ascii=False)
    body = json.dumps({
        "model": SF_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 1000,
        "temperature": 0.3,
    }).encode("utf-8")
    req = urllib.request.Request(
        SF_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        return None
    try:
        content = data["choices"][0]["message"]["content"].strip()
        # strip markdown fence if present
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        arr = json.loads(content)
    except Exception as e:
        print(f"LLM JSON parse failed: {e}\nraw: {content[:300] if 'content' in locals() else '?'}", file=sys.stderr)
        return None
    out = {}
    for item in arr:
        slug = item.get("slug")
        chip = item.get("result_chip")
        if slug and (chip in VALID_CHIPS or chip is None):
            out[slug] = chip
    return out


def collect_cards(vault: Path, limit: int | None = None) -> list:
    cards = []
    for p in vault.rglob("*.md"):
        if any(skip in p.parts for skip in ("_trash", "_quarantine", ".karpathy-wiki")):
            continue
        if p.name in ("_CLAUDE.md", "README.md", "MEMORY.md"):
            continue
        try:
            post = frontmatter.load(p)
        except Exception:
            continue
        if post.metadata.get("result_chip") is not None:
            continue  # 已 backfill 过,skip
        title = post.metadata.get("title") or p.stem
        snippet = post.content.strip()[:600]
        cards.append({"path": p, "slug": p.stem, "title": title, "snippet": snippet, "post": post})
        if limit and len(cards) >= limit:
            break
    return cards


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="real write (default dry-run)")
    ap.add_argument("--limit", type=int, default=None, help="cap cards processed")
    ap.add_argument("--vault", type=str, default="/vol1/1000/sift/users/1/vault", help="vault root")
    ap.add_argument("--batch", type=int, default=5, help="batch size per LLM call")
    args = ap.parse_args()

    vault = Path(args.vault)
    if not vault.exists():
        print(f"vault not found: {vault}", file=sys.stderr)
        sys.exit(1)

    cards = collect_cards(vault, limit=args.limit)
    print(f"collected {len(cards)} cards needing result_chip backfill")
    if not cards:
        return

    log_path = vault.parent / "_reports" / f"backfill-result-chip-{time.strftime('%Y-%m-%d')}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = open(log_path, "a", encoding="utf-8")
    log.write(f"\n=== run at {time.strftime('%Y-%m-%d %H:%M:%S')} (apply={args.apply}) ===\n")

    chips_assigned = 0
    null_count = 0
    failed_batches = 0

    for i in range(0, len(cards), args.batch):
        batch = cards[i:i + args.batch]
        result = call_llm_batch(batch)
        if result is None:
            failed_batches += 1
            log.write(f"BATCH {i}: LLM call failed\n")
            continue
        for c in batch:
            chip = result.get(c["slug"])
            line = f"  {c['slug']}: {chip!r}"
            print(line)
            log.write(line + "\n")
            if chip is None:
                null_count += 1
                continue
            chips_assigned += 1
            if args.apply:
                c["post"].metadata["result_chip"] = chip
                try:
                    with open(c["path"], "wb") as f:
                        frontmatter.dump(c["post"], f)
                except Exception as e:
                    log.write(f"    WRITE FAIL: {e}\n")
        log.flush()

    summary = (
        f"\nsummary: assigned={chips_assigned} null={null_count} "
        f"failed_batches={failed_batches} total={len(cards)} "
        f"apply={args.apply}\n"
    )
    print(summary)
    log.write(summary)
    log.close()


if __name__ == "__main__":
    main()
