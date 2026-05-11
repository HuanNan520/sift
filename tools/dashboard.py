#!/usr/bin/env python3
"""Sift vault health dashboard — single-page HTML report.

Usage:
    dashboard.py [vault-path] [--out FILE] [--title "..."]

Default: scan cwd, write to stdout.

Renders:
  - 4 KPI cards (total / schema compliance / healthy / avg remaining life)
  - Card type distribution (donut)
  - Expiration timeline by month (heatmap)
  - Frontmatter field coverage (bars)
  - Next 10 expiring (table)

Zero external dependencies in the output — inline SVG + CSS, no CDN.
Dark Tokyo Night palette, Noto Sans SC + JetBrains Mono fallbacks.

Requires: python3, pyyaml.
"""
import sys
import os
import re
import glob
import argparse
import subprocess
import math
import html as _html
from datetime import date, datetime
from collections import defaultdict, Counter


def parse_frontmatter(path):
    import yaml

    class StringDateLoader(yaml.SafeLoader):
        pass
    StringDateLoader.add_constructor(
        'tag:yaml.org,2002:timestamp',
        lambda loader, node: loader.construct_scalar(node)
    )

    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return None

    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.load(m.group(1), Loader=StringDateLoader)
    except yaml.YAMLError:
        return None


def scan_vault(vault):
    for type_dir in ('research', 'debug', 'scripts', 'decisions'):
        for path in sorted(glob.glob(os.path.join(vault, 'skills', type_dir, '*.md'))):
            if path.endswith('.template.md'):
                continue
            fm = parse_frontmatter(path)
            if fm is None:
                continue
            yield os.path.relpath(path, vault), type_dir, fm


def run_lint(vault):
    """Run lint.sh and parse 'X/Y cards passed'. Returns (pass, total)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    lint_path = os.path.join(os.path.dirname(script_dir), 'lint.sh')
    if not os.path.isfile(lint_path):
        return 0, 0
    try:
        result = subprocess.run(
            [lint_path, vault],
            capture_output=True, text=True, timeout=60
        )
        m = re.search(r'(\d+)/(\d+)\s+cards passed', result.stdout)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return 0, 0


def compute_stats(vault):
    cards = list(scan_vault(vault))
    today = date.today()

    type_counts = Counter()
    field_coverage = {'expires': 0, 'recheck-trigger': 0, 'tags': 0,
                      'ai-first': 0, 'problem': 0}
    expires_dates = []

    for rel, td, fm in cards:
        type_counts[td] += 1
        for fld in field_coverage:
            if fld in fm:
                field_coverage[fld] += 1
        if 'expires' in fm:
            try:
                exp = datetime.strptime(
                    str(fm['expires']).strip().strip("'\""),
                    '%Y-%m-%d'
                ).date()
                days = (exp - today).days
                expires_dates.append((rel, td, exp, days, fm))
            except (ValueError, AttributeError):
                pass

    month_buckets = defaultdict(int)
    for rel, td, exp, days, fm in expires_dates:
        month_buckets[exp.strftime('%Y-%m')] += 1

    expired = sum(1 for _, _, _, d, _ in expires_dates if d < 0)
    nearing = sum(1 for _, _, _, d, _ in expires_dates if 0 <= d <= 30)
    healthy = sum(1 for _, _, _, d, _ in expires_dates if d > 30)
    avg_days = (sum(d for _, _, _, d, _ in expires_dates) // len(expires_dates)
                if expires_dates else 0)

    expires_dates.sort(key=lambda x: x[3])
    top10 = [
        (rel, td, exp.strftime('%Y-%m-%d'), d,
         str(fm.get('problem') or fm.get('context')
             or fm.get('purpose') or '')[:90])
        for rel, td, exp, d, fm in expires_dates[:10]
    ]

    lint_pass, lint_total = run_lint(vault)

    return {
        'total': len(cards),
        'type_counts': dict(type_counts),
        'lint_pass': lint_pass,
        'lint_total': lint_total or len(cards),
        'compliance_pct': round(lint_pass / (lint_total or 1) * 100, 1),
        'expired': expired,
        'nearing': nearing,
        'healthy': healthy,
        'avg_remaining_days': avg_days,
        'field_coverage': field_coverage,
        'month_buckets': dict(sorted(month_buckets.items())),
        'top10': top10,
    }


# === SVG generators ===

CARD_COLORS = {
    'research':  '#7aa2f7',
    'debug':     '#f7768e',
    'scripts':   '#9ece6a',
    'decisions': '#e0af68',
}


def donut_svg(type_counts):
    total = sum(type_counts.values()) or 1
    cx, cy, r_o, r_i = 120, 120, 100, 60
    parts = ['<svg viewBox="0 0 240 240" width="240" height="240" '
             'role="img" aria-label="card type distribution">']

    if total == 0:
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r_o}" '
                     f'fill="#1a1b26" stroke="#787c99" stroke-width="2"/>')
    else:
        start = -90.0
        for td in ('research', 'debug', 'scripts', 'decisions'):
            count = type_counts.get(td, 0)
            if count == 0:
                continue
            sweep = 360.0 * count / total
            end = start + sweep
            a1, a2 = math.radians(start), math.radians(end)
            x1, y1 = cx + r_o * math.cos(a1), cy + r_o * math.sin(a1)
            x2, y2 = cx + r_o * math.cos(a2), cy + r_o * math.sin(a2)
            x3, y3 = cx + r_i * math.cos(a2), cy + r_i * math.sin(a2)
            x4, y4 = cx + r_i * math.cos(a1), cy + r_i * math.sin(a1)
            large = 1 if sweep > 180 else 0
            if sweep >= 359.9:
                # full circle, render as ring
                path = (f'M {cx-r_o} {cy} '
                        f'A {r_o} {r_o} 0 1 0 {cx+r_o} {cy} '
                        f'A {r_o} {r_o} 0 1 0 {cx-r_o} {cy} '
                        f'M {cx-r_i} {cy} '
                        f'A {r_i} {r_i} 0 1 1 {cx+r_i} {cy} '
                        f'A {r_i} {r_i} 0 1 1 {cx-r_i} {cy}')
                parts.append(
                    f'<path d="{path}" fill="{CARD_COLORS[td]}" '
                    f'fill-rule="evenodd"><title>{td}: {count}</title></path>')
            else:
                path = (f'M {x1:.2f} {y1:.2f} '
                        f'A {r_o} {r_o} 0 {large} 1 {x2:.2f} {y2:.2f} '
                        f'L {x3:.2f} {y3:.2f} '
                        f'A {r_i} {r_i} 0 {large} 0 {x4:.2f} {y4:.2f} Z')
                parts.append(
                    f'<path d="{path}" fill="{CARD_COLORS[td]}" '
                    f'stroke="#1a1b26" stroke-width="2">'
                    f'<title>{td}: {count}</title></path>')
            start = end

    parts.append(f'<text x="{cx}" y="{cy-2}" text-anchor="middle" '
                 f'fill="#a9b1d6" font-size="32" font-weight="700" '
                 f'font-family="\'JetBrains Mono\',monospace">{total}</text>')
    parts.append(f'<text x="{cx}" y="{cy+22}" text-anchor="middle" '
                 f'fill="#787c99" font-size="12">cards</text>')
    parts.append('</svg>')
    return ''.join(parts)


def heatmap_svg(month_buckets):
    if not month_buckets:
        return ('<div style="color:#787c99;padding:24px 0;">'
                'no expires data to visualize</div>')
    max_count = max(month_buckets.values())
    months = list(month_buckets.keys())
    cell_w, cell_h = 64, 44
    width = cell_w * len(months) + 16
    height = cell_h + 32
    parts = [f'<svg viewBox="0 0 {width} {height}" '
             f'width="100%" height="{height}" preserveAspectRatio="xMinYMid meet" '
             f'role="img" aria-label="expiration timeline by month">']
    for i, ym in enumerate(months):
        c = month_buckets[ym]
        # gradient from card-bg toward warm color
        intensity = c / max_count
        r = int(36 + intensity * 220)
        g = int(40 + intensity * 90)
        b = int(60 + intensity * 80)
        x = i * cell_w + 8
        parts.append(
            f'<rect x="{x}" y="0" width="{cell_w-6}" height="{cell_h}" '
            f'fill="rgb({r},{g},{b})" rx="6" ry="6">'
            f'<title>{ym}: {c} card{"" if c==1 else "s"} expire</title></rect>'
        )
        parts.append(
            f'<text x="{x + (cell_w-6)/2}" y="{cell_h/2+6}" '
            f'text-anchor="middle" fill="#fff" '
            f'font-family="\'JetBrains Mono\',monospace" '
            f'font-size="15" font-weight="700">{c}</text>'
        )
        parts.append(
            f'<text x="{x + (cell_w-6)/2}" y="{cell_h+18}" '
            f'text-anchor="middle" fill="#787c99" font-size="11" '
            f'font-family="\'JetBrains Mono\',monospace">{ym}</text>'
        )
    parts.append('</svg>')
    return ''.join(parts)


def bar_svg(field_coverage, total):
    fields = ['expires', 'recheck-trigger', 'tags', 'ai-first', 'problem']
    bar_h = 28
    spacing = 12
    label_w = 140
    chart_w = 360
    value_w = 110
    width = label_w + chart_w + value_w + 8
    height = (bar_h + spacing) * len(fields) + 8
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" '
             f'height="{height}" preserveAspectRatio="xMinYMid meet" '
             f'role="img" aria-label="frontmatter field coverage">']
    for i, fld in enumerate(fields):
        count = field_coverage.get(fld, 0)
        pct = (count / total) if total else 0
        y = i * (bar_h + spacing)
        bar_w = pct * chart_w
        parts.append(
            f'<text x="0" y="{y+bar_h/2+5}" fill="#a9b1d6" font-size="13" '
            f'font-family="\'JetBrains Mono\',monospace">{fld}</text>'
        )
        parts.append(
            f'<rect x="{label_w}" y="{y}" width="{chart_w}" '
            f'height="{bar_h}" fill="#1a1b26" rx="4"/>'
        )
        if bar_w > 0:
            color = '#9ece6a' if pct >= 0.9 else '#7aa2f7' if pct >= 0.5 else '#e0af68'
            parts.append(
                f'<rect x="{label_w}" y="{y}" width="{bar_w}" '
                f'height="{bar_h}" fill="{color}" rx="4"/>'
            )
        parts.append(
            f'<text x="{label_w+chart_w+10}" y="{y+bar_h/2+5}" '
            f'fill="#a9b1d6" font-size="13" '
            f'font-family="\'JetBrains Mono\',monospace">'
            f'{count}/{total} ({int(pct*100)}%)</text>'
        )
    parts.append('</svg>')
    return ''.join(parts)


def render_html(stats, vault, title):
    legend_items = []
    for td in ('research', 'debug', 'scripts', 'decisions'):
        c = stats['type_counts'].get(td, 0)
        legend_items.append(
            f'<div class="legend-item">'
            f'<span class="legend-dot" style="background:{CARD_COLORS[td]}"></span>'
            f'<span>{td}</span>'
            f'<span class="legend-count">{c}</span>'
            f'</div>'
        )

    top10_rows = []
    for rel, td, exp, days, prob in stats['top10']:
        if days < 0:
            days_color = '#f7768e'
            days_str = f'{-days} days ago'
        elif days <= 30:
            days_color = '#e0af68'
            days_str = f'in {days} days'
        else:
            days_color = '#a9b1d6'
            days_str = f'in {days} days'
        top10_rows.append(f'''
            <tr>
              <td class="path">{_html.escape(rel)}</td>
              <td><span class="badge type-{td}">{td}</span></td>
              <td class="expires">{exp}</td>
              <td class="days" style="color:{days_color}">{days_str}</td>
              <td class="problem">{_html.escape(prob)}</td>
            </tr>''')

    compliance_kpi_cls = (
        'good' if stats['compliance_pct'] >= 95
        else 'warn' if stats['compliance_pct'] >= 80
        else 'bad'
    )
    health_kpi_cls = (
        'good' if stats['expired'] == 0 and stats['nearing'] == 0
        else 'warn' if stats['expired'] == 0
        else 'bad'
    )

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_html.escape(title)}</title>
<style>
  :root {{
    --bg: #1a1b26; --card: #24283b; --fg: #a9b1d6; --muted: #787c99;
    --blue: #7aa2f7; --cyan: #7dcfff; --green: #9ece6a;
    --yellow: #e0af68; --red: #f7768e;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 32px 16px; background: var(--bg); color: var(--fg);
    font-family: 'Noto Sans SC', -apple-system, 'Segoe UI', sans-serif;
    font-size: 14px; line-height: 1.6;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .hero {{ margin-bottom: 32px; }}
  .hero h1 {{
    margin: 0 0 8px; color: #fff; font-size: 28px; font-weight: 700;
    letter-spacing: -0.5px;
  }}
  .hero .meta {{ color: var(--muted); font-size: 13px; }}
  .hero .meta code {{
    font-family: 'JetBrains Mono', ui-monospace, monospace;
    color: var(--cyan);
  }}
  .intro {{
    background: var(--card); border-radius: 12px;
    padding: 20px 24px; margin-bottom: 24px;
    border-left: 3px solid var(--blue);
  }}
  .intro h3 {{
    margin: 0 0 10px; color: #fff; font-size: 13px;
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600;
  }}
  .intro p {{ margin: 6px 0; color: var(--fg); font-size: 13px; }}
  .intro .legend-inline {{
    display: flex; flex-wrap: wrap; gap: 18px; margin-top: 10px;
    color: var(--muted); font-size: 12px;
  }}
  .intro .legend-inline span {{ display: inline-flex; align-items: center; gap: 6px; }}
  .intro .legend-inline .dot {{
    width: 10px; height: 10px; border-radius: 50%;
  }}
  .kpi-row {{
    display: grid; grid-template-columns: repeat(4, 1fr);
    gap: 16px; margin-bottom: 32px;
  }}
  .kpi {{ background: var(--card); border-radius: 12px; padding: 24px; }}
  .kpi-label {{
    color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600;
  }}
  .kpi-value {{
    color: #fff; font-size: 36px; font-weight: 700; margin: 10px 0 4px;
    font-family: 'JetBrains Mono', monospace; letter-spacing: -1px;
  }}
  .kpi-sub {{ color: var(--muted); font-size: 12px; }}
  .kpi-sub code {{
    font-family: 'JetBrains Mono', monospace; color: var(--cyan);
  }}
  .kpi-hint {{
    margin-top: 12px; padding-top: 12px;
    border-top: 1px solid rgba(255,255,255,0.05);
    color: var(--muted); font-size: 11px; line-height: 1.5;
  }}
  .kpi.good .kpi-value {{ color: var(--green); }}
  .kpi.warn .kpi-value {{ color: var(--yellow); }}
  .kpi.bad .kpi-value {{ color: var(--red); }}
  .panel {{
    background: var(--card); border-radius: 12px;
    padding: 24px; margin-bottom: 20px;
  }}
  .panel h2 {{
    margin: 0 0 6px; color: #fff; font-size: 15px; font-weight: 600;
    letter-spacing: 0.2px;
  }}
  .panel .hint {{
    margin: 0 0 18px; color: var(--muted); font-size: 12px; line-height: 1.6;
  }}
  .panel .hint code {{
    font-family: 'JetBrains Mono', monospace; color: var(--cyan); font-size: 11px;
  }}
  .action-row {{
    margin-top: 28px; padding: 20px 24px; background: var(--card);
    border-radius: 12px; border-left: 3px solid var(--green);
  }}
  .action-row h3 {{
    margin: 0 0 12px; color: #fff; font-size: 13px;
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600;
  }}
  .action-row ul {{ margin: 0; padding-left: 22px; color: var(--fg); }}
  .action-row li {{ margin: 4px 0; font-size: 13px; line-height: 1.7; }}
  .action-row code {{
    background: var(--bg); padding: 2px 6px; border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    color: var(--cyan); font-size: 12px;
  }}
  .panel-row {{
    display: grid; grid-template-columns: 240px 1fr;
    gap: 24px; align-items: center;
  }}
  .legend {{ display: flex; flex-direction: column; gap: 10px; }}
  .legend-item {{
    display: flex; align-items: center; gap: 12px; font-size: 13px;
  }}
  .legend-dot {{
    width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
  }}
  .legend-count {{
    margin-left: auto; color: var(--muted);
    font-family: 'JetBrains Mono', monospace;
  }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 12px; }}
  th {{
    color: var(--muted); font-weight: 600; font-size: 11px;
    text-transform: uppercase; letter-spacing: 0.5px;
    border-bottom: 1px solid var(--bg);
  }}
  td {{ border-bottom: 1px solid #1a1b26; }}
  tbody tr:last-child td {{ border-bottom: none; }}
  .path {{
    font-family: 'JetBrains Mono', monospace; color: var(--cyan);
    font-size: 12px; word-break: break-all;
  }}
  .expires, .days {{ font-family: 'JetBrains Mono', monospace; }}
  .problem {{
    color: var(--muted); max-width: 320px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }}
  .badge {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-family: 'JetBrains Mono', monospace;
  }}
  .type-research  {{ background: rgba(122,162,247,0.18); color: var(--blue); }}
  .type-debug     {{ background: rgba(247,118,142,0.18); color: var(--red); }}
  .type-scripts   {{ background: rgba(158,206,106,0.18); color: var(--green); }}
  .type-decisions {{ background: rgba(224,175,104,0.18); color: var(--yellow); }}
  .footer {{
    text-align: center; color: var(--muted); font-size: 12px; margin-top: 40px;
  }}
  .footer a {{ color: var(--blue); text-decoration: none; }}
  .footer code {{
    font-family: 'JetBrains Mono', monospace; color: var(--cyan);
  }}
  @media (max-width: 900px) {{
    .kpi-row {{ grid-template-columns: repeat(2, 1fr); }}
    .panel-row {{ grid-template-columns: 1fr; }}
    .problem {{ display: none; }}
  }}
  @media (max-width: 480px) {{
    body {{ padding: 16px 12px; }}
    .kpi-row {{ grid-template-columns: 1fr; }}
    .hero h1 {{ font-size: 22px; }}
    .kpi-value {{ font-size: 28px; }}
    table {{ font-size: 12px; }}
    th, td {{ padding: 8px 6px; }}
  }}
</style>
</head>
<body>
<div class="container">

  <div class="hero">
    <h1>{_html.escape(title)}</h1>
    <div class="meta">
      vault: <code>{_html.escape(vault)}</code> ·
      scanned at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    </div>
  </div>

  <div class="intro">
    <h3>这份报告告诉你什么 · What this report says</h3>
    <p>sift 把 AI 帮你解过的有用的事沉淀成「会过期、能复核」的卡片。这份报告扫了你 vault 里所有卡片,告诉你三件事:</p>
    <p>① 这堆卡是不是<b>合规的</b>(能被 sift 工具消费) · ② 哪些卡<b>快到期 / 已过期</b>(需要复核是否仍成立) · ③ 沉淀<b>种类分布</b>(你最近在解什么类型的问题)。</p>
    <div class="legend-inline">
      <span><span class="dot" style="background:var(--green)"></span>绿 = 健康</span>
      <span><span class="dot" style="background:var(--yellow)"></span>黄 = 快到期 / 接近阈值</span>
      <span><span class="dot" style="background:var(--red)"></span>红 = 要立即处理</span>
    </div>
  </div>

  <div class="kpi-row">
    <div class="kpi">
      <div class="kpi-label">total cards · 卡片总数</div>
      <div class="kpi-value">{stats['total']}</div>
      <div class="kpi-sub">across 4 type folders</div>
      <div class="kpi-hint">vault 的体量。应稳定增长;长期不涨说明 AI 协作没在沉淀。</div>
    </div>
    <div class="kpi {compliance_kpi_cls}">
      <div class="kpi-label">schema compliance · 规范合规率</div>
      <div class="kpi-value">{stats['compliance_pct']}%</div>
      <div class="kpi-sub">{stats['lint_pass']}/{stats['lint_total']} pass <code>lint.sh</code></div>
      <div class="kpi-hint">通过 sift 校验的占比。≥95% 健康 · &lt;95% 跑 <code>tools/lint.sh</code> 查具体哪张卡。</div>
    </div>
    <div class="kpi {health_kpi_cls}">
      <div class="kpi-label">healthy cards · 健康卡数</div>
      <div class="kpi-value">{stats['healthy']}</div>
      <div class="kpi-sub">{stats['expired']} expired · {stats['nearing']} expiring &lt;30d</div>
      <div class="kpi-hint">30 天内不会到期的卡。已过期 / 近过期数字越大 = 越快需要复核。</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">avg remaining life · 平均剩余寿命</div>
      <div class="kpi-value">{stats['avg_remaining_days']}<span style="font-size:18px;color:var(--muted);margin-left:4px;">d</span></div>
      <div class="kpi-sub">across cards with <code>expires</code></div>
      <div class="kpi-hint">距离 expires 的天数均值。&gt;180 天健康 · &lt;60 天 = 该批量重核了。</div>
    </div>
  </div>

  <div class="panel">
    <h2>Card type distribution · 卡片类型分布</h2>
    <p class="hint">看你最近沉淀的<b>方向</b>。<code>debug</code> 多 = 在修 bug · <code>research</code> 多 = 在调研 · <code>decisions</code> 多 = 在做架构决策 · <code>scripts</code> 多 = 在攒可复用片段。比例严重失衡说明协作模式可能跑偏。</p>
    <div class="panel-row">
      <div>{donut_svg(stats['type_counts'])}</div>
      <div class="legend">
        {''.join(legend_items)}
      </div>
    </div>
  </div>

  <div class="panel">
    <h2>Expiration timeline · 未来过期分布(按月)</h2>
    <p class="hint">每个色块 = 该月有多少张卡到期。色越红越深 = 集中度越高 = 那个月要提前安排复核时间。空 = 那个月没东西需要重核。</p>
    {heatmap_svg(stats['month_buckets'])}
  </div>

  <div class="panel">
    <h2>Frontmatter field coverage · 关键字段覆盖率</h2>
    <p class="hint">sift 要求 research / debug / decisions 三类卡必须有 <code>expires</code> 和 <code>recheck-trigger</code> 字段(否则没法过期复核)。绿条(&gt;90%) = 合规 · 黄条(&lt;50%) = 大量卡缺关键字段需补。</p>
    {bar_svg(stats['field_coverage'], stats['total'])}
  </div>

  <div class="panel">
    <h2>Next 10 expiring · 最近 10 张到期</h2>
    <p class="hint">按距离过期的天数升序。红字 = <b>已过期</b>(立即重核) · 黄字 = <b>30 天内到期</b> · 白字 = 较远。直接照着列表跑 <code>tools/recheck.sh</code> 或人工挨张过。</p>
    <table>
      <thead><tr>
        <th>path</th><th>type</th><th>expires</th><th>in</th><th>about</th>
      </tr></thead>
      <tbody>{''.join(top10_rows) if top10_rows else '<tr><td colspan="5" style="color:#787c99;text-align:center;padding:24px;">no cards with expires</td></tr>'}</tbody>
    </table>
  </div>

  <div class="action-row">
    <h3>看到这些数字应该做什么 · What to do</h3>
    <ul>
      <li>看到 <b>schema compliance &lt; 100%</b> → 跑 <code>./tools/lint.sh ~/your-vault/</code> 看是哪张卡的字段不对,改完再扫</li>
      <li>看到 <b>有红/黄数字</b>(已过期 / 近过期) → 跑 <code>./tools/recheck.sh --within-days 30 ~/your-vault/</code> 出待办列表挨张过</li>
      <li>看到 <b>某月色块异常深</b> → 提前把那个月的复核排进 calendar,别等真到期才一次性爆掉</li>
      <li>看到 <b>字段覆盖率黄/红条</b> → 大量旧卡缺 expires / recheck-trigger,挨张补字段并设触发条件</li>
      <li>不了解卡片格式 → 看 <a href="https://github.com/HuanNan520/sift/blob/main/SPEC_zh.md" style="color:var(--blue);">SPEC_zh.md 中文规范</a> 或 <a href="https://github.com/HuanNan520/sift/blob/main/QUICKSTART_zh.md" style="color:var(--blue);">5 分钟快速开始</a></li>
    </ul>
  </div>

  <div class="footer">
    generated by <code>tools/dashboard.py</code> ·
    <a href="https://github.com/HuanNan520/sift">sift</a> spec
  </div>

</div>
</body>
</html>'''


def main():
    parser = argparse.ArgumentParser(
        description="Sift vault health dashboard — single-page HTML"
    )
    parser.add_argument('vault', nargs='?', default='.',
                        help='Vault path (default: cwd)')
    parser.add_argument('--out', help='Output HTML file (default: stdout)')
    parser.add_argument('--title', default='Sift vault health',
                        help='Page title (default: "Sift vault health")')
    args = parser.parse_args()

    vault = os.path.abspath(args.vault)
    stats = compute_stats(vault)
    html = render_html(stats, vault, args.title)

    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'wrote: {args.out} ({len(html)} bytes)', file=sys.stderr)
    else:
        print(html)


if __name__ == '__main__':
    main()
