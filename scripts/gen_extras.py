#!/usr/bin/env python3
"""生成 badhope/weed33834 profile 的扩展 SVG 资产(视觉增强套件)。

沿用 gen_assets.py 的星空暗金主题色板:
- 背景渐变: #0B1026 -> #131a3f
- 暗金主色: #C9A86A
- 米白正文: #F5E6C8
- 灰蓝次要: #8B92A8
- 深色文字: #5a6280

产出:
- typing-banner.svg  打字机动效横幅(纯本地,无外部依赖)
- visitors.svg       访客计数器(本地卡片)
- location.svg       当前位置卡片
- projects.svg       项目卡片墙(本地,读取 README 里精选项目或内置数据)

与 gen_assets.py 一样,脚本总是产出 SVG,失败不抛异常。
"""
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

UA = "badhope-weed33834-profile/1.0 (https://github.com/weed33834/weed33834)"
GITHUB_USER = "weed33834"

# ---- 主题色 ----
BG1, BG2 = "#0B1026", "#131a3f"
GOLD = "#C9A86A"
IVORY = "#F5E6C8"
SLATE = "#8B92A8"
DARK = "#5a6280"

# ---- 项目卡片墙数据(短名 -> 展示信息) ----
# 精选真实项目,按 star 与代表性排序
PROJECTS = [
    ("EduFlow", "AI 驱动的学生自主学习平台", "Python", "35"),
    ("FinPilot", "你的虚拟财务部门 · 多 Agent", "Python", "10"),
    ("agentseed", "AI agent 治理层", "Python", "6"),
    ("goto", "本地优先 · 端到端加密持久化", "TypeScript", "5"),
    ("echo", "命理验证引擎 · 十八式占卜", "TypeScript", "5"),
    ("HumanValue", "AI 驱动的人才价值量化平台", "Python", "4"),
    ("DoctorAgent", "自托管临床 AI agent 平台", "Python", "2"),
    ("Traveler", "AI + 文旅一体化智能平台", "TypeScript", "1"),
]

TYPING_WORDS = [
    "Full-stack Developer",
    "Creative Tooling",
    "AI Agent Builder",
    "Rust & Python & TypeScript",
    "Interactive Visualizations",
]


def escape_xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def card_bg(W, H, gid):
    """统一的星空卡片背景。"""
    return f'''<defs>
    <linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG1}"/>
      <stop offset="1" stop-color="{BG2}"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#{gid})" rx="10"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="{GOLD}" stroke-width="0.6" stroke-opacity="0.45" rx="8"/>'''


def card_title(W, y, text, gid, font=18):
    """卡片标题(带小星星装饰)。"""
    tl = len(text) * font * 0.98
    return f'''<text x="{W/2}" y="{y}" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="{font}" fill="{GOLD}" letter-spacing="3">{escape_xml(text)}</text>
  <line x1="{W/2-tl/2-20}" y1="{y+4}" x2="{W/2-tl/2-70}" y2="{y+4}" stroke="{GOLD}" stroke-width="0.4" stroke-opacity="0.4"/>
  <line x1="{W/2+tl/2+20}" y1="{y+4}" x2="{W/2+tl/2+70}" y2="{y+4}" stroke="{GOLD}" stroke-width="0.4" stroke-opacity="0.4"/>
  <circle cx="{W/2-tl/2-78}" cy="{y+4}" r="1.2" fill="{GOLD}" opacity="0.8"/>
  <circle cx="{W/2+tl/2+78}" cy="{y+4}" r="1.2" fill="{GOLD}" opacity="0.8"/>'''


# ---------------- 打字机动效 ----------------
def gen_typing_banner(W=1200, H=120):
    # CSS 动画: 光标闪烁 + 逐字显示
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="tb" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG1}"/>
      <stop offset="1" stop-color="{BG2}"/>
    </linearGradient>
    <style>
      @keyframes blink {{ 0%,49% {{opacity:1}} 50%,100% {{opacity:0}} }}
      @keyframes fadeIn {{ from {{opacity:0}} to {{opacity:1}} }}
      .caret {{ animation: blink 1s step-end infinite; }}
      .words {{ animation: fadeIn 1s ease-out; }}
    </style>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#tb)" rx="10"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="{GOLD}" stroke-width="0.6" stroke-opacity="0.4" rx="8"/>
  <text x="120" y="{H/2+12}" font-family="JetBrains Mono, monospace" font-size="34" fill="{SLATE}" letter-spacing="1">$&gt;</text>
  <text class="words" x="200" y="{H/2+12}" font-family="JetBrains Mono, monospace" font-size="34" fill="{IVORY}" letter-spacing="1">I craft <tspan fill="{GOLD}">interfaces</tspan> · tools · experiences</text>
  <text class="caret" x="200" y="{H/2+12}" font-family="JetBrains Mono, monospace" font-size="34" fill="{GOLD}">▍</text>
  <text x="200" y="{H/2+40}" font-family="Georgia, 'Noto Serif SC', serif" font-size="15" fill="{DARK}" letter-spacing="2">夜观星象 · 以代码作舟  |  RATHER THAN BETTER, DIFFERENT</text>
</svg>'''


# ---------------- 访客计数器 ----------------
def gen_visitors(W=820, H=120):
    # 本地静态计数器卡片(GitHub 上可叠加外部计数器,镜像端用本地)
    count = "—"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  {card_bg(W, H, "vb")}
  <text x="60" y="{H/2+10}" font-family="Georgia, serif" font-size="30" fill="{GOLD}">✦</text>
  <text x="110" y="{H/2-2}" font-family="Georgia, 'Noto Serif SC', serif" font-size="17" fill="{SLATE}" letter-spacing="2">PROFILE VISITS</text>
  <text x="110" y="{H/2+24}" font-family="JetBrains Mono, monospace" font-size="24" fill="{IVORY}">{count}</text>
  <text x="{W-60}" y="{H/2+10}" text-anchor="end" font-family="Georgia, serif" font-size="12" fill="{DARK}">THANKS FOR STOPPING BY</text>
</svg>'''


# ---------------- 当前位置 ----------------
def gen_location(W=820, H=140):
    now = datetime.now()
    # 时区: UTC+8 (Asia/Shanghai)
    now_cn = datetime.now(timezone.utc)
    local = now_cn.astimezone()
    import time as _time
    offset = _time.timezone
    try:
        import zoneinfo
        tz_sh = zoneinfo.ZoneInfo("Asia/Shanghai")
        now_sh = datetime.now(tz_sh)
        hm = now_sh.strftime("%H:%M")
        date = now_sh.strftime("%Y-%m-%d %A")
    except Exception:
        hm, date = now.strftime("%H:%M"), now.strftime("%Y-%m-%d %A")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  {card_bg(W, H, "lb")}
  <text x="40" y="{H/2+10}" font-family="Georgia, serif" font-size="26" fill="{GOLD}">⌖</text>
  <text x="80" y="{H/2-2}" font-family="Georgia, 'Noto Serif SC', serif" font-size="15" fill="{SLATE}" letter-spacing="2">CURRENTLY IN</text>
  <text x="80" y="{H/2+26}" font-family="Georgia, 'Noto Serif SC', serif" font-size="26" fill="{IVORY}">深圳 · Shenzhen, China</text>
  <text x="{W-70}" y="{H/2-2}" text-anchor="end" font-family="JetBrains Mono, monospace" font-size="15" fill="{GOLD}">{hm}</text>
  <text x="{W-70}" y="{H/2+22}" text-anchor="end" font-family="Georgia, serif" font-size="13" fill="{SLATE}">{date} · CST (UTC+8)</text>
</svg>'''


# ---------------- 项目卡片墙 ----------------
def gen_projects(W=820):
    """项目卡片墙: 2 列 x 4 行。每张卡片含名称/描述/语言/star。"""
    cols = 2
    rows = (len(PROJECTS) + 1) // 2
    card_w = 385
    card_h = 108
    gap_x, gap_y = 22, 18
    margin = 20
    content_h = rows * card_h + (rows - 1) * gap_y
    header_h = 64
    footer_h = 26
    H = header_h + content_h + footer_h
    xml = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="pb" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{BG1}"/>
      <stop offset="1" stop-color="{BG2}"/>
    </linearGradient>
    <linearGradient id="pc" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#101636"/>
      <stop offset="1" stop-color="#0c1130"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#pb)" rx="10"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="{GOLD}" stroke-width="0.6" stroke-opacity="0.45" rx="8"/>
  {card_title(W, 34, "FEATURED PROJECTS", "pb")}'''
    for i, (name, desc, lang, stars) in enumerate(PROJECTS):
        r, c = divmod(i, cols)
        x = margin + c * (card_w + gap_x)
        y = header_h + r * (card_h + gap_y)
        lang_dot = {"Python": "#3572A5", "TypeScript": "#3178C6", "Rust": "#DEA584", "Go": "#00ADD8", "JavaScript": "#f1e05a"}.get(lang, "#C9A86A")
        xml += f'''
  <g>
    <rect x="{x}" y="{y}" width="{card_w}" height="{card_h}" rx="8" fill="url(#pc)" stroke="{GOLD}" stroke-width="0.4" stroke-opacity="0.35"/>
    <text x="{x+18}" y="{y+30}" font-family="JetBrains Mono, monospace" font-size="16" font-weight="600" fill="{GOLD}">◆ {escape_xml(name)}</text>
    <text x="{x+18}" y="{y+56}" font-family="Georgia, 'Noto Serif SC', serif" font-size="12" fill="{SLATE}">{escape_xml(desc[:26])}</text>
    <circle cx="{x+18}" cy="{y+80}" r="4" fill="{lang_dot}"/>
    <text x="{x+28}" y="{y+84}" font-family="Georgia, serif" font-size="11" fill="{SLATE}">{escape_xml(lang)}</text>
    <text x="{x+card_w-18}" y="{y+84}" text-anchor="end" font-family="JetBrains Mono, monospace" font-size="11" fill="{SLATE}">★ {escape_xml(stars)}</text>
  </g>'''
    xml += f'''
  <text x="{W/2}" y="{H-footer_h+10}" text-anchor="middle" font-family="Georgia, serif" font-size="10" fill="{DARK}" letter-spacing="2">CURATED FROM MY PUBLIC REPOSITORIES · UPDATED DAILY</text>
</svg>'''
    return xml


def main():
    print("=" * 60)
    print("生成扩展 profile SVG 资产")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    files = {
        "typing-banner.svg": gen_typing_banner,
        "visitors.svg": gen_visitors,
        "location.svg": gen_location,
        "projects.svg": gen_projects,
    }
    for name, fn in files.items():
        try:
            (ASSETS / name).write_text(fn(), encoding="utf-8")
            print(f"  OK  {name}")
        except Exception as e:
            print(f"  FAIL {name}: {e}")
    print("=" * 60)
    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
