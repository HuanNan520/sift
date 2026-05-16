#!/usr/bin/env python3
"""
sift 投喂入口 · 抓 URL 内容 → AI 写卡 → 进 vault

支持:
  - B 站 (yt-dlp · 优先字幕 · 没字幕用元数据)
  - 抖音 (yt-dlp 元数据 · ASR 暂未配)
  - YouTube (yt-dlp 字幕)
  - 微信文章 (readability)
  - 知乎 (readability)
  - 任意网页 (readability)
"""
import re
import os
import json
import requests
import yt_dlp
from pathlib import Path
from datetime import datetime
from readability import Document
from bs4 import BeautifulSoup

LLM_API_URL = os.environ.get("LLM_API_URL", "https://api.deepseek.com/v1/chat/completions")
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("SILICONFLOW_API_KEY") or ""
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-chat")

# Per-user storage layout (v1 SaaS multi-tenant).
# Callers pass uid; the path is built at write time.
SIFT_USERS_ROOT = Path(os.environ.get("SIFT_USERS_ROOT", "/vol1/1000/sift/users"))


def _user_ingest_dir(uid: int) -> Path:
    p = SIFT_USERS_ROOT / str(int(uid)) / "vault" / "ingest"
    p.mkdir(parents=True, exist_ok=True)
    return p


def detect_platform(url: str) -> str:
    if "bilibili.com" in url or "b23.tv" in url:
        return "bilibili"
    if "douyin.com" in url or "iesdouyin.com" in url:
        return "douyin"
    if "mp.weixin.qq.com" in url:
        return "wechat"
    if "zhihu.com" in url:
        return "zhihu"
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "xiaohongshu.com" in url or "xhslink.com" in url:
        return "xiaohongshu"
    return "web"


def fetch_video(url: str) -> dict:
    """B 站 / YouTube / 抖音 · yt-dlp 拿元数据 + 字幕"""
    opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["zh-Hans", "zh-CN", "zh", "en"],
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    title = info.get("title") or ""
    description = (info.get("description") or "")[:1500]
    uploader = info.get("uploader") or info.get("channel") or ""
    duration = info.get("duration", 0)

    # 字幕(优先 manual · 然后 auto)
    subs = info.get("subtitles") or {}
    auto_subs = info.get("automatic_captions") or {}
    subtitle_text = ""

    for source in (subs, auto_subs):
        if subtitle_text:
            break
        for lang in ("zh-Hans", "zh-CN", "zh", "en"):
            if lang not in source:
                continue
            for sub in source[lang]:
                if sub.get("ext") in ("vtt", "json3"):
                    try:
                        r = requests.get(sub["url"], timeout=15)
                        subtitle_text = _clean_vtt(r.text)
                        if subtitle_text:
                            break
                    except Exception:
                        continue
            if subtitle_text:
                break

    return {
        "title": title,
        "description": description,
        "uploader": uploader,
        "duration": duration,
        "subtitle": subtitle_text,
    }


def _clean_vtt(vtt: str) -> str:
    """简单 VTT 清洗成纯文本"""
    lines = []
    for line in vtt.split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT") or "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        if line:
            lines.append(line)
    return "\n".join(lines)[:10000]


def fetch_web(url: str) -> dict:
    """通用网页抓取 · 微信 / 知乎 / 任意"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"

    doc = Document(r.text)
    title = doc.title() or ""
    summary_html = doc.summary()
    soup = BeautifulSoup(summary_html, "lxml")

    # 提取干净文本
    for tag in soup(["script", "style", "noscript", "iframe", "form"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    text = re.sub(r"\n\s*\n", "\n\n", text).strip()

    return {
        "title": title,
        "content": text[:10000],
    }


SINK_PROMPT = """你是 sift 投喂代理 · 用户给你一个链接 · 你帮他把内容整理成一张知识卡。

## 来源
{source_info}

## 内容(字幕 / 文章正文)
{content}

## 任务

输出一张完整的 markdown 卡片 · 严格遵守这个结构:

```
---
type: ingest
source: {url}
platform: {platform}
title: <用户视角的简练标题 · 不照搬原标题 · ≤ 30 字>
date: {today}
tags: [<3-5 个核心标签 · 中文短词 · 用方括号 yaml list 格式>]
---

> <一句话核心 · ≤ 50 字 · 让用户一秒知道这张卡讲啥>

## 关键点

- <要点 1 · 提炼不复制>
- <要点 2>
- <要点 3-5 条 · 简练>

## 你可能想问

- <深入问题 1 · 帮用户启发>
- <深入问题 2>

## 关联线索

- <可能跟用户 vault 哪些主题相关 · 3 条以内>
```

## 风格要求

- 像私人助理给的笔记 · 不像 ChatGPT 模板
- 中文 · 简练 · ≤ 600 字
- frontmatter 必须合法 yaml
- 标签是真实主题 · 不要泛词('知识''学习'这种)

只输出 markdown(包含 frontmatter)· 不要任何解释 · 不要代码块包装。
"""


def llm_write_card(content_dict: dict) -> str:
    """调 DeepSeek 把内容整理成 sift 卡"""
    today = datetime.now().strftime("%Y-%m-%d")
    text = content_dict.get("subtitle") or content_dict.get("content") or content_dict.get("description", "")
    if not text.strip():
        text = f"标题: {content_dict.get('title', '')}\n描述: {content_dict.get('description', '')}"

    source_info_lines = [f"URL: {content_dict['url']}"]
    if content_dict.get("platform"):
        source_info_lines.append(f"平台: {content_dict['platform']}")
    if content_dict.get("title"):
        source_info_lines.append(f"原标题: {content_dict['title']}")
    if content_dict.get("uploader"):
        source_info_lines.append(f"作者: {content_dict['uploader']}")
    if content_dict.get("duration"):
        m = content_dict["duration"] // 60
        s = content_dict["duration"] % 60
        source_info_lines.append(f"时长: {m}:{s:02d}")

    prompt = SINK_PROMPT.format(
        source_info="\n".join(source_info_lines),
        content=text[:10000],
        url=content_dict["url"],
        platform=content_dict.get("platform", "web"),
        today=today,
    )

    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 未配置 · 检查 /vol1/1000/sift/.env")

    r = requests.post(
        LLM_API_URL,
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "你是 sift 知识沉淀助手 · 输出严格的 markdown。"},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 2000,
            "temperature": 0.5,
        },
        timeout=90,
    )
    r.raise_for_status()
    data = r.json()
    md = data["choices"][0]["message"]["content"].strip()

    # 去掉可能的 markdown 代码块包装
    md = re.sub(r"^```(?:markdown|md)?\n", "", md)
    md = re.sub(r"\n```\s*$", "", md)
    return md.strip()


def slug_from_title(title: str) -> str:
    slug = re.sub(r"[^\w一-鿿぀-ヿ가-힯-]", "-", title)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:60] or "untitled"


def extract_title_from_md(md: str) -> str:
    m = re.search(r"^title:\s*(.+?)$", md, re.M)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    return ""


def ingest_url(url: str, uid: int = 1) -> dict:
    """主入口 · 投喂一个 URL · 返回 slug / path / title。uid 决定卡片落在哪个用户的 vault/ingest/。"""
    url = url.strip()
    if not url:
        raise ValueError("URL 不能为空")
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url

    platform = detect_platform(url)

    # 1. 抓内容
    if platform in ("bilibili", "youtube", "douyin"):
        try:
            data = fetch_video(url)
        except Exception as e:
            # 视频抓不到 · 退到通用网页抓元数据
            try:
                data = fetch_web(url)
            except Exception:
                raise RuntimeError(f"内容抓取失败: {e}")
    else:
        data = fetch_web(url)

    data["url"] = url
    data["platform"] = platform

    if not data.get("title") and not data.get("content") and not data.get("subtitle"):
        raise RuntimeError("链接内容为空 · 可能需要登录或被反爬")

    # 2. LLM 写卡
    md_card = llm_write_card(data)

    # 3. 保存
    today = datetime.now().strftime("%Y-%m-%d")
    title_str = extract_title_from_md(md_card) or data.get("title", "投喂卡")[:60]
    slug = f"{today}-{slug_from_title(title_str)}"

    # 避免重名
    ingest_dir = _user_ingest_dir(uid)
    out_path = ingest_dir / f"{slug}.md"
    counter = 1
    while out_path.exists():
        out_path = ingest_dir / f"{slug}-{counter}.md"
        counter += 1

    out_path.write_text(md_card, encoding="utf-8")

    return {
        "slug": out_path.stem,
        "path": str(out_path),
        "platform": platform,
        "title": title_str,
        "url": url,
    }


if __name__ == "__main__":
    # CLI 测试
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 ingest.py <url>")
        sys.exit(1)
    result = ingest_url(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
