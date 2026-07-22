#!/usr/bin/env python3
"""生成 badhope/weed33834 profile README 的 SVG 资产。

- banner.svg     顶部星空横幅(静态)
- quote.svg      每日一言(在线 hitokoto.cn,失败回退本地库)
- onthisday.svg  历史上的今天(在线 Wikipedia REST API,失败回退占位)
- divider.svg    分割线装饰(静态)

GitHub Action 每天 UTC 00:00 自动跑一次,刷新 quote.svg / onthisday.svg,
然后 commit 到 main 并同步推送到 GitCode badhope/badhope。

健壮性策略:
1. 每个 API 调用带 timeout + 重试(3 次,指数退避)
2. 多数据源容错:hitokoto 失败用本地 25 条库;Wikipedia 失败用中文维基;都失败用占位
3. XML 转义防 SVG 渲染崩溃
4. 失败不抛异常,总是产出 SVG(保证 README 永远有内容)
5. 退出码:0=至少一个在线源成功,1=全部回退(供 Action 判断)
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
    qt = escape_xml(quote_text)
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
    print("\n[1/4] 生成 banner.svg(静态)...")
    (ASSETS / "banner.svg").write_text(gen_banner(), encoding="utf-8")
    print("  OK")

    print("\n[2/4] 生成 divider.svg(静态)...")
    (ASSETS / "divider.svg").write_text(gen_divider(), encoding="utf-8")
    print("  OK")

    # 一言
    print("\n[3/4] 生成 quote.svg(在线 hitokoto.cn)...")
    q_text, q_author, q_source = fetch_quote()
    (ASSETS / "quote.svg").write_text(gen_quote(q_text, q_author, q_source), encoding="utf-8")
    print(f"  source={q_source}")
    print(f"  text: {q_text}")
    print(f"  author: {q_author}")

    # 历史上的今天
    print("\n[4/4] 生成 onthisday.svg(在线 Wikipedia)...")
    now = datetime.now(timezone.utc)
    mm, dd = f"{now.month:02d}", f"{now.day:02d}"
    events, ot_source = fetch_on_this_day()
    (ASSETS / "onthisday.svg").write_text(gen_onthisday(events, ot_source, mm, dd), encoding="utf-8")
    print(f"  source={ot_source}: {len(events)} events on {mm}/{dd}")
    for y, t in events:
        print(f"    {y}: {t[:70]}")

    # 退出码:0=至少一个在线源成功,1=全部回退
    all_fallback = q_source.startswith("local-fallback") and ot_source == "all-sources-failed"
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
