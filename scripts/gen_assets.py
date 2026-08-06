#!/usr/bin/env python3
"""生成 badhope/weed33834 profile README 的 SVG 资产。

- banner.svg       顶部星空横幅(静态)
- quote.svg        每日一言(在线 hitokoto.cn,失败回退本地库)
- onthisday.svg    历史上的今天(在线 Wikipedia REST API,失败回退占位)
- divider.svg      分割线装饰(静态)
- stats.svg        GitHub 统计卡片(在线 GitHub API,失败回退上次缓存)
- languages.svg    语言占比环形图(在线 GitHub API,失败回退上次缓存)

GitHub Action 每天 UTC 00:00 自动跑一次,刷新 quote.svg / onthisday.svg / stats.svg / languages.svg,
然后 commit 到 main。镜像仓库通过手动同步维护。

健壮性策略:
1. 每个 API 调用带 timeout + 重试(3 次,指数退避)
2. 多数据源容错:hitokoto 失败用本地 25 条库;Wikipedia 失败用中文维基;都失败用占位
3. XML 转义防 SVG 渲染崩溃
4. 失败不抛异常,总是产出 SVG(保证 README 永远有内容)
5. 退出码:0=至少一个在线源成功,1=全部回退(供 Action 判断)
6. stats.svg / languages.svg 失败时保留上次缓存的文件,避免 README 出现断裂
"""
import json
import random
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ASSETS.mkdir(exist_ok=True)

UA = "badhope-weed33834-profile/1.0 (https://github.com/weed33834/weed33834)"

# ---------- 本地名言库(hitokoto 失败时回退) ----------
FALLBACK_QUOTES = [
    ("星光不问赶路人,时光不负有心人。", "佚名"),
    ("我们都在阴沟里,但仍有人仰望星空。", "王尔德"),
    ("代码是写给人看的,只是顺便能在机器上运行。", "Harold Abelson"),
    ("不要因为走得太远,而忘记为什么出发。", "纪伯伦"),
    ("简单是可靠的先决条件。", "Edsger Dijkstra"),
    ("与其更好,不如不同。", "彼得·蒂尔"),
    ("夜观星象,以知天命;日写代码,以尽人事。", "badhope/weed33834"),
    ("慢就是稳,稳就是快。", "海豹突击队"),
    ("Stay hungry, stay foolish.", "Steve Jobs"),
    ("做难事必有所得。", "钱穆"),
    ("最好的代码,是没有代码。", "Jeff Atwood"),
    ("不积跬步,无以至千里。", "荀子"),
    ("理想主义者在夜空下从不孤单。", "佚名"),
    ("Talk is cheap, show me the code.", "Linus Torvalds"),
    ("纸上得来终觉浅,绝知此事要躬行。", "陆游"),
    ("一期一会,世当珍惜。", "千利休"),
    ("纵有疾风起,人生不言弃。", "宫崎骏"),
    ("黑夜给了我黑色的眼睛,我却用它寻找光明。", "顾城"),
    ("完美不是无可增加,而是无可删减。", "圣埃克苏佩里"),
    ("行到水穷处,坐看云起时。", "王维"),
    ("万物皆有裂痕,那是光照进来的地方。", "莱昂纳德·科恩"),
    ("种一棵树最好的时间是十年前,其次是现在。", "谚语"),
    ("山高路远,看世界,也找自己。", "佚名"),
    ("当你凝视深渊时,深渊也在凝视你。", "尼采"),
    ("程序的浪漫,在于它精确地执行你的想象。", "佚名"),
]


# ---------- HTTP 工具 ----------
def http_get_json(url, timeout=12, retries=3, backoff=1.5):
    """带重试和指数退避的 HTTP GET JSON。"""
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            last_err = e
            if attempt < retries - 1:
                wait = backoff ** (attempt + 1)
                print(f"  [retry {attempt+1}/{retries}] {type(e).__name__}: {e} -> wait {wait:.1f}s")
                time.sleep(wait)
    raise last_err


def escape_xml(s):
    """转义 XML 特殊字符,防止 SVG 渲染炸掉。"""
    if not s:
        return ""
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def text_width(s):
    """估算文本宽度(中文2,英文1)。"""
    return sum(2 if ord(c) > 127 else 1 for c in s)


def wrap_text(s, max_width):
    """按估算宽度换行,返回行列表。"""
    if not s:
        return [""]
    # 按空格分词(英文)或逐字(中文)
    words = s.split(" ") if " " in s else list(s)
    lines = []
    current = ""
    for w in words:
        sep = " " if current and " " in s else ""
        test = current + sep + w if current else w
        if text_width(test) <= max_width or not current:
            current = test
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def tspan_lines(text, x, y, max_width, font_size, line_height_factor=1.3):
    """生成带换行的 <tspan> SVG 文本。返回 (tspan_xml, total_height)。"""
    lines = wrap_text(escape_xml(text), max_width)
    lh = font_size * line_height_factor
    tspans = ""
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else lh
        tspans += f'<tspan x="{x}" dy="{dy:.1f}">{line}</tspan>'
    total_h = len(lines) * lh
    return tspans, total_h


# ---------- 一言 ----------
def fetch_quote():
    """在线拉取 hitokoto.cn 一言(诗词+哲学),失败按日确定性回退到本地库。

    返回 (text, author, source)。
    """
    try:
        d = http_get_json("https://v1.hitokoto.cn/?c=i&c=k&encode=json", timeout=10, retries=3)
        text = (d.get("hitokoto") or "").strip()
        if not text:
            raise ValueError("empty hitokoto")
        author = d.get("from_who") or d.get("from") or "佚名"
        source = d.get("from") or ""
        # 若作者与出处一致,只保留一个;否则组合
        if source and author != source and author != "佚名":
            author = f"{author}·《{source}》"
        elif source and (author == "佚名" or not author):
            author = f"《{source}》"
        return text, author or "佚名", "hitokoto.cn"
    except Exception as e:
        print(f"  [quote] hitokoto 失败: {type(e).__name__}: {e} -> 用本地库")
        today = datetime.now(timezone.utc).timetuple().tm_yday
        q = FALLBACK_QUOTES[today % len(FALLBACK_QUOTES)]
        return q[0], q[1], f"local-fallback({type(e).__name__})"


# ---------- 历史上的今天 ----------
def fetch_on_this_day():
    """在线拉取 Wikipedia On This Day events,挑 3 条最古老的。

    先试英文维基,失败试中文维基,都失败返回空列表 + 占位。
    返回 (events, source)。events: list of (year, text)。
    """
    now = datetime.now(timezone.utc)
    mm, dd = f"{now.month:02d}", f"{now.day:02d}"

    # 数据源列表:英文维基优先(事件更全),中文维基备选
    sources = [
        (
            f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm}/{dd}",
            "wikipedia-en",
            "en",
        ),
        (
            f"https://zh.wikipedia.org/api/rest_v1/feed/onthisday/events/{mm}/{dd}",
            "wikipedia-zh",
            "zh",
        ),
    ]

    for url, label, lang in sources:
        try:
            d = http_get_json(url, timeout=15, retries=2)
            events = d.get("events", [])
            if not events:
                print(f"  [onthisday] {label} 返回空事件列表")
                continue
            # 按年份升序,取最早 3 条(更有"历史厚度")
            events.sort(key=lambda e: e.get("year", 9999))
            out = []
            for e in events[:3]:
                year = e.get("year")
                text = (e.get("text") or "").strip()
                # 截断过长文本(英文维基偶尔有长段落)
                if len(text) > 120:
                    text = text[:117] + "..."
                if year and text:
                    out.append((year, text))
            if out:
                return out, label
            print(f"  [onthisday] {label} 解析后无有效事件")
        except Exception as e:
            print(f"  [onthisday] {label} 失败: {type(e).__name__}: {e}")
            continue

    return [], "all-sources-failed"


# ---------- 星空 SVG 工具 ----------
def rand_stars(w, h, count, rng, min_r=0.3, max_r=1.5, min_o=0.25, max_o=1.0, sparkle=True):
    out = []
    for _ in range(count):
        x = rng.uniform(0, w)
        y = rng.uniform(0, h)
        r = rng.uniform(min_r, max_r)
        o = rng.uniform(min_o, max_o)
        if sparkle and rng.random() < 0.1 and r > 0.9:
            out.append(
                f'<g opacity="{o:.2f}"><circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#F5E6C8"/>'
                f'<path d="M{x-r*3.5:.1f},{y:.1f} L{x+r*3.5:.1f},{y:.1f} M{x:.1f},{y-r*3.5:.1f} L{x:.1f},{y+r*3.5:.1f}" stroke="#F5E6C8" stroke-width="0.35" opacity="0.6"/></g>'
            )
        else:
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#F5E6C8" opacity="{o:.2f}"/>'
            )
    return "\n  ".join(out)


def galaxy_band(w, h, rng, count=60):
    out = []
    a, b = -0.35, h * 0.7
    for _ in range(count):
        x = rng.uniform(0, w)
        y = a * x + b + rng.gauss(0, 22)
        if 0 <= y <= h:
            r = rng.uniform(0.3, 1.1)
            o = rng.uniform(0.3, 0.85)
            out.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="#F5E6C8" opacity="{o:.2f}"/>'
            )
    return "\n  ".join(out)


# ---------- SVG 生成 ----------
def gen_banner():
    rng = random.Random(42)
    W, H = 1200, 320
    nebula = ""
    for cx, cy, r, col, op in [
        (900, 80, 220, "#C9A86A", 0.10),
        (250, 260, 180, "#3a4a8c", 0.18),
        (1050, 250, 160, "#8c6a3a", 0.08),
    ]:
        nebula += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{col}" opacity="{op}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto" preserveAspectRatio="xMidYMid slice">
  <defs>
    <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#06081A"/>
      <stop offset="0.55" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#sky)"/>
  {nebula}
  {galaxy_band(W, H, rng, 70)}
  {rand_stars(W, H, 70, rng)}
  <line x1="70" y1="28" x2="250" y2="150" stroke="#F5E6C8" stroke-width="1.1" stroke-linecap="round" opacity="0.55"/>
  <line x1="80" y1="30" x2="120" y2="58" stroke="#F5E6C8" stroke-width="2" stroke-linecap="round" opacity="0.9"/>
  <line x1="920" y1="18" x2="1060" y2="100" stroke="#F5E6C8" stroke-width="0.9" stroke-linecap="round" opacity="0.5"/>
  <g stroke="#C9A86A" stroke-width="0.65" stroke-opacity="0.55" fill="none">
    <line x1="975" y1="55" x2="1040" y2="88"/>
    <line x1="1040" y1="88" x2="1095" y2="68"/>
    <line x1="1095" y1="68" x2="1140" y2="108"/>
    <line x1="1040" y1="88" x2="1078" y2="142"/>
    <line x1="1078" y1="142" x2="1135" y2="162"/>
    <line x1="1078" y1="142" x2="1015" y2="172"/>
  </g>
  <g fill="#F5E6C8">
    <circle cx="975" cy="55" r="2.2"/>
    <circle cx="1040" cy="88" r="2.8"/>
    <circle cx="1095" cy="68" r="2.0"/>
    <circle cx="1140" cy="108" r="2.4"/>
    <circle cx="1078" cy="142" r="3.0"/>
    <circle cx="1135" cy="162" r="2.0"/>
    <circle cx="1015" cy="172" r="2.2"/>
  </g>
  <text x="600" y="168" text-anchor="middle" font-family="Georgia, 'Times New Roman', 'Noto Serif SC', serif" font-size="60" font-weight="500" fill="#F5E6C8" letter-spacing="3">badhope<tspan fill="#C9A86A" font-weight="600">/</tspan>weed33834</text>
  <text x="600" y="206" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="20" font-style="italic" fill="#8B92A8" letter-spacing="7">夜 观 星 象 · 以 代 码 作 舟</text>
  <line x1="430" y1="246" x2="588" y2="246" stroke="#C9A86A" stroke-width="0.5" stroke-opacity="0.55"/>
  <line x1="612" y1="246" x2="770" y2="246" stroke="#C9A86A" stroke-width="0.5" stroke-opacity="0.55"/>
  <path d="M594 240 L600 246 L594 252 M606 240 L600 246 L606 252" fill="none" stroke="#C9A86A" stroke-width="0.7" stroke-opacity="0.8"/>
  <circle cx="600" cy="246" r="1.6" fill="#C9A86A"/>
</svg>'''


def gen_quote(quote_text, author, source):
    au = escape_xml(author)
    # 长文本自动换行
    max_w = 44
    lines = wrap_text(quote_text, max_w)
    font_size = 22 if len(lines) <= 1 else 19 if len(lines) == 2 else 16
    lh = font_size * 1.35
    total_h = len(lines) * lh
    start_y = 108 - total_h / 2 + font_size * 0.8
    tspans = ""
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else lh
        tspans += f'<tspan x="410" dy="{dy:.1f}">{escape_xml(line)}</tspan>'
    H = 210 if total_h < 100 else 210 + (total_h - 100)
    author_y = start_y + total_h + 20
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="qbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="820" height="{H}" fill="url(#qbg)" rx="6"/>
  <rect x="6" y="6" width="808" height="{H-12}" fill="none" stroke="#C9A86A" stroke-width="0.6" stroke-opacity="0.5" rx="4"/>
  <path d="M14 14 L36 14 M14 14 L14 36" stroke="#C9A86A" stroke-width="1" fill="none"/>
  <path d="M806 14 L784 14 M806 14 L806 36" stroke="#C9A86A" stroke-width="1" fill="none"/>
  <path d="M14 {H-14} L36 {H-14} M14 {H-14} L14 {H-36}" stroke="#C9A86A" stroke-width="1" fill="none"/>
  <path d="M806 {H-14} L784 {H-14} M806 {H-14} L806 {H-36}" stroke="#C9A86A" stroke-width="1" fill="none"/>
  <text x="44" y="86" font-family="Georgia, serif" font-size="76" fill="#C9A86A" fill-opacity="0.32">&#8220;</text>
  <text x="410" y="{start_y:.1f}" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="{font_size}" fill="#F5E6C8" letter-spacing="2">{tspans}</text>
  <text x="760" y="{author_y:.1f}" text-anchor="end" font-family="Georgia, serif" font-size="14" font-style="italic" fill="#8B92A8">— {au}</text>
  <text x="410" y="{H-18}" text-anchor="middle" font-family="Georgia, serif" font-size="10" fill="#5a6280" letter-spacing="1.5">via {escape_xml(source)}</text>
</svg>'''


def gen_onthisday(events, source, mm, dd):
    """历史上的今天卡片。events: list of (year, text)。自动换行防溢出。"""
    # 动态计算高度:每个事件可能有多行
    font_size = 13
    year_font_size = 15
    max_text_width = 56  # 估算字符宽度(x=100 到 780,约 56 个英文字符宽)
    line_h = font_size * 1.4

    rows_xml = ""
    current_y = 78
    event_blocks = []
    for year, text in events:
        tspans, h = tspan_lines(text, 100, current_y, max_text_width, font_size)
        event_blocks.append((year, current_y, tspans, h))
        current_y += h + 16  # 事件间距

    if not events:
        H = 130
        placeholder = '<text x="410" y="100" text-anchor="middle" font-family="Georgia, serif" font-size="14" fill="#5a6280" font-style="italic">历史此刻,数据未达。</text>'
    else:
        H = current_y + 30

    rows_xml = ""
    for year, y_pos, tspans, h in event_blocks:
        rows_xml += f'''
  <text x="40" y="{y_pos}" font-family="JetBrains Mono, monospace" font-size="{year_font_size}" fill="#C9A86A" font-weight="500">{escape_xml(str(year))}</text>
  <text x="100" y="{y_pos}" font-family="Georgia, 'Noto Serif SC', serif" font-size="{font_size}" fill="#F5E6C8">{tspans}</text>'''

    placeholder = "" if events else placeholder
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 820 {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="obg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="820" height="{H}" fill="url(#obg)" rx="6"/>
  <rect x="6" y="6" width="808" height="{H-12}" fill="none" stroke="#C9A86A" stroke-width="0.6" stroke-opacity="0.5" rx="4"/>
  <text x="410" y="40" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="20" fill="#C9A86A" letter-spacing="3">历史上的今天 · {escape_xml(mm)}/{escape_xml(dd)}</text>
  <line x1="280" y1="52" x2="540" y2="52" stroke="#C9A86A" stroke-width="0.4" stroke-opacity="0.4"/>{rows_xml}
  {placeholder}
  <text x="410" y="{H-10}" text-anchor="middle" font-family="Georgia, serif" font-size="10" fill="#5a6280" letter-spacing="1.5">via {escape_xml(source)} · Wikipedia On This Day</text>
</svg>'''


# ---------- GitHub 统计 ----------
GITHUB_USER = "weed33834"
GITHUB_TOKEN_ENV = "GH_STATS_TOKEN"


def fetch_github_user():
    """在线拉取 GitHub 用户公开统计,失败返回 None。"""
    import os
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(
            f"https://api.github.com/users/{GITHUB_USER}",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"  [stats] GitHub API 失败: {type(e).__name__}: {e}")
        return None


def fetch_github_repos():
    """拉取用户所有公开仓库(含 fork),用于统计 stars/forks。"""
    import os
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    repos = []
    page = 1
    while True:
        try:
            url = f"https://api.github.com/users/{GITHUB_USER}/repos?per_page=100&page={page}&type=owner"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as r:
                batch = json.loads(r.read().decode("utf-8"))
                if not batch:
                    break
                repos.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
        except Exception as e:
            print(f"  [repos] GitHub API 失败: {type(e).__name__}: {e}")
            break
    return repos


def fetch_github_languages(repos):
    """拉取所有非 fork 仓库的语言数据,返回 {lang: bytes} 字典。"""
    import os
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    headers = {"User-Agent": UA, "Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    lang_totals = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        owner = repo["owner"]["login"]
        name = repo["name"]
        try:
            url = f"https://api.github.com/repos/{owner}/{name}/languages"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as r:
                langs = json.loads(r.read().decode("utf-8"))
                for lang, b in langs.items():
                    lang_totals[lang] = lang_totals.get(lang, 0) + b
        except Exception:
            pass
    return lang_totals


# 语言配色 (GitHub Linguist 风格 + 暗金主题适配)
LANG_COLORS = {
    "Python": "#3776AB",
    "TypeScript": "#3178C6",
    "JavaScript": "#F7DF1E",
    "CSS": "#563D7C",
    "Vue": "#41B883",
    "HTML": "#E34F26",
    "Rust": "#DEA584",
    "Shell": "#89E051",
    "Dockerfile": "#384D54",
    "Go": "#00ADD8",
    "MDX": "#1B1C1D",
    "Stata": "#1F4E79",
}


# ---------- 贡献热力图 ----------
def fetch_contributions():
    """通过 GitHub GraphQL API 拉取贡献日历数据。"""
    import os
    token = os.environ.get(GITHUB_TOKEN_ENV, "")
    if not token:
        print("  [contrib] 无 token,跳过")
        return None
    query = """query {
  user(login: "%s") {
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      totalIssueContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
      pullRequests(states: MERGED, first: 10) { totalCount }
    }
  }
}""" % GITHUB_USER
    headers = {
        "Authorization": f"bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": UA,
    }
    try:
        body = json.dumps({"query": query}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=body,
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        cc = data["data"]["user"]["contributionsCollection"]
        return cc
    except Exception as e:
        print(f"  [contrib] GraphQL 失败: {type(e).__name__}: {e}")
        return None


def gen_contributions(cc_data):
    """生成贡献热力图 SVG。"""
    if not cc_data:
        return None
    cal = cc_data.get("contributionCalendar", {})
    weeks = cal.get("weeks", [])
    total = cal.get("totalContributions", 0)
    if not weeks:
        return None

    commits = cc_data.get("totalCommitContributions", 0)
    prs = cc_data.get("totalPullRequestContributions", 0)
    pr_reviews = cc_data.get("totalPullRequestReviewContributions", 0)
    issues = cc_data.get("totalIssueContributions", 0)
    new_repos = cc_data.get("totalRepositoryContributions", 0)
    merged_prs = cc_data.get("pullRequests", {}).get("totalCount", 0)

    max_count = 1
    for w in weeks:
        for day in w["contributionDays"]:
            if day["contributionCount"] > max_count:
                max_count = day["contributionCount"]

    CELL = 11
    GAP = 2
    MARGIN_L = 50
    MARGIN_T = 40
    MARGIN_R = 16
    MARGIN_B = 45
    num_weeks = len(weeks)
    W = MARGIN_L + num_weeks * (CELL + GAP) + MARGIN_R
    H = MARGIN_T + 7 * (CELL + GAP) + MARGIN_B

    # Dark gold palette: 5 levels
    LEVEL_COLORS = ["#161b2e", "#2a3117", "#5c4a1a", "#8a6e28", "#C9A86A"]

    def level_for(count):
        if count == 0:
            return 0
        ratio = count / max_count
        if ratio <= 0.25:
            return 1
        elif ratio <= 0.5:
            return 2
        elif ratio <= 0.75:
            return 3
        return 4

    cells = ""
    for wi, week in enumerate(weeks):
        x = MARGIN_L + wi * (CELL + GAP)
        for di, day in enumerate(week["contributionDays"]):
            y = MARGIN_T + di * (CELL + GAP)
            lvl = level_for(day["contributionCount"])
            color = LEVEL_COLORS[lvl]
            cells += f'  <rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}"/>\n'

    # Month labels
    month_labels = ""
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    last_month = -1
    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            date_str = day["date"]
            month = int(date_str[5:7])
            if month != last_month and day["contributionCount"] is not None:
                x = MARGIN_L + wi * (CELL + GAP)
                month_labels += f'  <text x="{x}" y="{MARGIN_T - 8}" font-family="Georgia, serif" font-size="9" fill="#8B92A8">{months[month - 1]}</text>\n'
                last_month = month
            break

    # Day labels (Mon/Wed/Fri)
    day_labels = ""
    for di, label in [(0, ""), (1, "Mon"), (2, ""), (3, "Wed"), (4, ""), (5, "Fri"), (6, "")]:
        if label:
            y = MARGIN_T + di * (CELL + GAP) + CELL - 1
            day_labels += f'  <text x="{MARGIN_L - 6}" y="{y}" text-anchor="end" font-family="Georgia, serif" font-size="8" fill="#8B92A8">{label}</text>\n'

    # Stats row at bottom
    stats_y = MARGIN_T + 7 * (CELL + GAP) + 18
    stats_items = [
        f"Total: {total}",
        f"Commits: {commits}",
        f"PRs: {prs}",
        f"Merged: {merged_prs}",
        f"Issues: {issues}",
        f"Repos: {new_repos}",
    ]
    stats_text = "  ".join(stats_items)

    # Legend
    legend_x = MARGIN_L
    legend_y = stats_y + 12
    legend = f'  <text x="{legend_x}" y="{legend_y}" font-family="Georgia, serif" font-size="9" fill="#8B92A8">Less</text>\n'
    for i in range(5):
        lx = legend_x + 30 + i * (CELL + GAP)
        legend += f'  <rect x="{lx}" y="{legend_y - 8}" width="{CELL}" height="{CELL}" rx="2" fill="{LEVEL_COLORS[i]}"/>\n'
    legend += f'  <text x="{legend_x + 30 + 5 * (CELL + GAP) + 4}" y="{legend_y}" font-family="Georgia, serif" font-size="9" fill="#8B92A8">More</text>\n'

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="cbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#cbg)" rx="6"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="#C9A86A" stroke-width="0.6" stroke-opacity="0.5" rx="4"/>
  <text x="{W//2}" y="22" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="14" fill="#C9A86A" letter-spacing="3">{total} contributions in the last year</text>
{month_labels}{day_labels}{cells}  <text x="{W//2}" y="{stats_y}" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="11" fill="#F5E6C8">{escape_xml(stats_text)}</text>
{legend}</svg>'''


def gen_languages(lang_data):
    """生成语言占比环形图 SVG。lang_data 为 {lang: bytes} 字典。"""
    if not lang_data:
        return None
    sorted_langs = sorted(lang_data.items(), key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in sorted_langs)
    if total == 0:
        return None

    # Top 6 + Other
    top = sorted_langs[:6]
    other_bytes = sum(v for _, v in sorted_langs[6:])
    if other_bytes > 0:
        top.append(("Other", other_bytes))

    W, H = 820, 200
    cx, cy, r_out, r_in = 180, 100, 75, 45

    import math
    angles = []
    cumulative = 0
    for lang, b in top:
        pct = b / total
        start = cumulative * 2 * math.pi - math.pi / 2
        cumulative += pct
        end = cumulative * 2 * math.pi - math.pi / 2
        angles.append((lang, pct, start, end))

    slices = ""
    for lang, pct, start, end in angles:
        color = LANG_COLORS.get(lang, "#8B92A8")
        x1 = cx + r_out * math.cos(start)
        y1 = cy + r_out * math.sin(start)
        x2 = cx + r_out * math.cos(end)
        y2 = cy + r_out * math.sin(end)
        large_arc = 1 if (end - start) > math.pi else 0
        xi1 = cx + r_in * math.cos(end)
        yi1 = cy + r_in * math.sin(end)
        xi2 = cx + r_in * math.cos(start)
        yi2 = cy + r_in * math.sin(start)
        slices += f'''  <path d="M{x1:.1f} {y1:.1f} A{r_out} {r_out} 0 {large_arc} 1 {x2:.1f} {y2:.1f} L{xi1:.1f} {yi1:.1f} A{r_in} {r_in} 0 {large_arc} 0 {xi2:.1f} {yi2:.1f} Z" fill="{color}" opacity="0.85"/>
'''

    legend = ""
    lx, ly = 340, 40
    for i, (lang, pct, _, _) in enumerate(angles):
        color = LANG_COLORS.get(lang, "#8B92A8")
        row = i // 2
        col = i % 2
        y_pos = ly + row * 32
        x_pos = lx + col * 240
        pct_str = f"{pct * 100:.1f}%"
        legend += f'''  <rect x="{x_pos}" y="{y_pos}" width="12" height="12" rx="2" fill="{color}" opacity="0.85"/>
  <text x="{x_pos + 18}" y="{y_pos + 11}" font-family="Georgia, serif" font-size="13" fill="#F5E6C8">{escape_xml(lang)}</text>
  <text x="{x_pos + 180}" y="{y_pos + 11}" font-family="JetBrains Mono, monospace" font-size="13" fill="#C9A86A" text-anchor="end">{pct_str}</text>
'''

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="lbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#lbg)" rx="6"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="#C9A86A" stroke-width="0.6" stroke-opacity="0.5" rx="4"/>
  <text x="{W//2}" y="28" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="16" fill="#C9A86A" letter-spacing="3">Most Used Languages</text>
  <line x1="280" y1="38" x2="540" y2="38" stroke="#C9A86A" stroke-width="0.4" stroke-opacity="0.4"/>
  <text x="{cx}" y="{cy + 5}" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="22" font-weight="600" fill="#C9A86A">{len(sorted_langs)}</text>
  <text x="{cx}" y="{cy + 22}" text-anchor="middle" font-family="Georgia, serif" font-size="9" fill="#8B92A8">langs</text>
{slices}{legend}
</svg>'''


def gen_stats(user_data, repos_data):
    """生成 GitHub 统计卡片 SVG。"""
    if user_data:
        repos = user_data.get("public_repos", 0)
        followers = user_data.get("followers", 0)
        following = user_data.get("following", 0)
        gists = user_data.get("public_gists", 0)
        source = "GitHub API"
    else:
        repos, followers, following, gists = 0, 0, 0, 0
        source = "unavailable"

    total_stars = sum(r.get("stargazers_count", 0) for r in repos_data) if repos_data else 0
    total_forks = sum(r.get("forks_count", 0) for r in repos_data) if repos_data else 0

    W, H = 820, 160
    items = [
        ("Repos", str(repos)),
        ("Stars", str(total_stars)),
        ("Followers", str(followers)),
        ("Forks", str(total_forks)),
    ]
    col_w = W // 4
    cols = ""
    for i, (label, value) in enumerate(items):
        cx = col_w * i + col_w // 2
        cols += f'''
  <text x="{cx}" y="72" text-anchor="middle" font-family="JetBrains Mono, monospace" font-size="34" font-weight="600" fill="#C9A86A">{escape_xml(value)}</text>
  <text x="{cx}" y="100" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="13" fill="#8B92A8" letter-spacing="1.5">{escape_xml(label)}</text>'''

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" height="auto">
  <defs>
    <linearGradient id="sbg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0B1026"/>
      <stop offset="1" stop-color="#131a3f"/>
    </linearGradient>
  </defs>
  <rect width="{W}" height="{H}" fill="url(#sbg)" rx="6"/>
  <rect x="6" y="6" width="{W-12}" height="{H-12}" fill="none" stroke="#C9A86A" stroke-width="0.6" stroke-opacity="0.5" rx="4"/>
  <text x="410" y="32" text-anchor="middle" font-family="Georgia, 'Noto Serif SC', serif" font-size="16" fill="#C9A86A" letter-spacing="3">GitHub Stats</text>
  <line x1="300" y1="42" x2="520" y2="42" stroke="#C9A86A" stroke-width="0.4" stroke-opacity="0.4"/>{cols}
  <text x="410" y="{H-12}" text-anchor="middle" font-family="Georgia, serif" font-size="9" fill="#5a6280" letter-spacing="1">via {escape_xml(source)}</text>
</svg>'''


def gen_divider():
    rng = random.Random(7)
    stars = "".join(
        f'<circle cx="{x:.1f}" cy="10" r="{rng.uniform(0.4,1.2):.2f}" fill="#C9A86A" opacity="{rng.uniform(0.3,0.9):.2f}"/>'
        for x in [rng.uniform(20, 170) for _ in range(8)]
        + [rng.uniform(230, 380) for _ in range(8)]
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 20" width="240" height="12">
  <line x1="20" y1="10" x2="170" y2="10" stroke="#C9A86A" stroke-width="0.4" stroke-opacity="0.5"/>
  <line x1="230" y1="10" x2="380" y2="10" stroke="#C9A86A" stroke-width="0.4" stroke-opacity="0.5"/>
  {stars}
  <path d="M190 6 L200 10 L190 14 M210 6 L200 10 L210 14" fill="none" stroke="#C9A86A" stroke-width="0.7"/>
  <circle cx="200" cy="10" r="1.4" fill="#C9A86A"/>
</svg>'''


def main():
    print("=" * 60)
    print("开始生成 profile SVG 资产")
    print(f"时间: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    # banner / divider 静态,但每次都重新写一遍以保证一致性
    print("\n[1/7] 生成 banner.svg(静态)...")
    (ASSETS / "banner.svg").write_text(gen_banner(), encoding="utf-8")
    print("  OK")

    print("\n[2/7] 生成 divider.svg(静态)...")
    (ASSETS / "divider.svg").write_text(gen_divider(), encoding="utf-8")
    print("  OK")

    # 一言
    print("\n[3/7] 生成 quote.svg(在线 hitokoto.cn)...")
    q_text, q_author, q_source = fetch_quote()
    (ASSETS / "quote.svg").write_text(gen_quote(q_text, q_author, q_source), encoding="utf-8")
    print(f"  source={q_source}")
    print(f"  text: {q_text}")
    print(f"  author: {q_author}")

    # 历史上的今天
    print("\n[4/7] 生成 onthisday.svg(在线 Wikipedia)...")
    now = datetime.now(timezone.utc)
    mm, dd = f"{now.month:02d}", f"{now.day:02d}"
    events, ot_source = fetch_on_this_day()
    (ASSETS / "onthisday.svg").write_text(gen_onthisday(events, ot_source, mm, dd), encoding="utf-8")
    print(f"  source={ot_source}: {len(events)} events on {mm}/{dd}")
    for y, t in events:
        print(f"    {y}: {t[:70]}")

    # GitHub 统计
    print("\n[5/8] 生成 stats.svg(在线 GitHub API)...")
    stats_path = ASSETS / "stats.svg"
    gh_user = fetch_github_user()
    gh_repos = fetch_github_repos() if gh_user else []
    if gh_user:
        stats_path.write_text(gen_stats(gh_user, gh_repos), encoding="utf-8")
        total_stars = sum(r.get("stargazers_count", 0) for r in gh_repos)
        print(f"  repos={gh_user.get('public_repos')} stars={total_stars} followers={gh_user.get('followers')}")
        stats_ok = True
    elif stats_path.exists():
        print("  GitHub API 失败,保留上次缓存的 stats.svg")
        stats_ok = False
    else:
        stats_path.write_text(gen_stats(None, []), encoding="utf-8")
        print("  GitHub API 失败,生成占位 stats.svg")
        stats_ok = False

    # 语言占比
    print("\n[6/8] 生成 languages.svg(在线 GitHub API)...")
    lang_path = ASSETS / "languages.svg"
    lang_data = fetch_github_languages(gh_repos) if gh_repos else {}
    lang_svg = gen_languages(lang_data) if lang_data else None
    if lang_svg:
        lang_path.write_text(lang_svg, encoding="utf-8")
        top3 = sorted(lang_data.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"  top3: {', '.join(f'{l}({b:,})' for l, b in top3)}")
        lang_ok = True
    elif lang_path.exists():
        print("  语言数据获取失败,保留上次缓存的 languages.svg")
        lang_ok = False
    else:
        print("  语言数据获取失败,且无缓存,跳过 languages.svg")
        lang_ok = False

    # 贡献热力图
    print("\n[7/8] 生成 contributions.svg(在线 GitHub GraphQL API)...")
    contrib_path = ASSETS / "contributions.svg"
    cc_data = fetch_contributions()
    contrib_svg = gen_contributions(cc_data) if cc_data else None
    if contrib_svg and cc_data:
        contrib_path.write_text(contrib_svg, encoding="utf-8")
        total_contrib = cc_data.get("contributionCalendar", {}).get("totalContributions", 0)
        commits = cc_data.get("totalCommitContributions", 0)
        merged = cc_data.get("pullRequests", {}).get("totalCount", 0)
        print(f"  total={total_contrib} commits={commits} merged_prs={merged}")
        contrib_ok = True
    elif contrib_path.exists():
        print("  贡献数据获取失败,保留上次缓存的 contributions.svg")
        contrib_ok = False
    else:
        print("  贡献数据获取失败,且无缓存,跳过 contributions.svg")
        contrib_ok = False
    # 清理无用文件
    print("\n[8/8] 清理...")
    print("  OK")

    # 退出码:0=至少一个在线源成功,1=全部回退
    all_fallback = q_source.startswith("local-fallback") and ot_source == "all-sources-failed" and not stats_ok and not lang_ok and not contrib_ok
    print("\n" + "=" * 60)
    if all_fallback:
        print("⚠ 全部数据源失败,使用回退内容。退出码 1。")
        print("=" * 60)
        return 1
    else:
        print("✓ 至少一个在线数据源成功。退出码 0。")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
