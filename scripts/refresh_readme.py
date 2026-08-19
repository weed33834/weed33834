#!/usr/bin/env python3
"""Refresh profile README with live GitHub projects, blog posts, and stats.

Runs in GitHub Actions on a schedule. Reads from GitHub API + CSDN RSS,
regenerates the marked-up blocks in the three localized README files, and
leaves the files changed so the workflow can commit them.
"""
import os
import re
import json
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

USER = "weed33834"
REPO = "weed33834"
CSDN_USER = "weixin_56622231"

TOP_N = int(os.environ.get("TOP_N", "6"))       # number of featured projects
BLOG_N = int(os.environ.get("BLOG_N", "5"))     # number of latest blog posts
ACTIVE_N = int(os.environ.get("ACTIVE_N", "5")) # number of recently-active repos


def gh(url):
    req = urllib.request.Request(url)
    req.add_header("Authorization", "token " + os.environ["GITHUB_TOKEN"])
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "readme-refresh-bot")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_projects():
    """Top N own (non-fork) repos by stars, then forks."""
    repos = gh(f"https://api.github.com/users/{USER}/repos?per_page=100&sort=updated")
    own = [r for r in repos if not r.get("fork") and r["name"] != REPO]
    own.sort(key=lambda r: (-r["stargazers_count"], -r["forks_count"]))
    lines = []
    for r in own[:TOP_N]:
        lang = r.get("language") or "—"
        lines.append(
            f'- ⭐ **[{r["name"]}]({r["html_url"]})** · {r["stargazers_count"]}★ · {lang}'
        )
    return "\n".join(lines)


def fetch_stats():
    """Text-only account stats: stars / followers / repos."""
    user = gh(f"https://api.github.com/users/{USER}")
    repos = gh(f"https://api.github.com/users/{USER}/repos?per_page=100")
    total_stars = sum(r["stargazers_count"] for r in repos)
    followers = user.get("followers", 0)
    repo_count = user.get("public_repos", 0)
    return (
        f"- ⭐ **{total_stars}** stars &nbsp;·&nbsp; "
        f"👥 **{followers}** followers &nbsp;·&nbsp; "
        f"📦 **{repo_count}** repositories"
    )


def fetch_blog():
    """Latest N posts from CSDN RSS."""
    url = f"https://blog.csdn.net/{CSDN_USER}/rss/list"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    xml = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    root = ET.fromstring(xml)
    lines = []
    for it in root.findall(".//item")[:BLOG_N]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate") or ""
        try:
            date = parsedate_to_datetime(pub).strftime("%Y-%m-%d")
        except Exception:
            date = pub[:16]
        if title and link:
            lines.append(f"- [{title}]({link}) · `{date}`")
    return "\n".join(lines)


def replace_block(txt, marker, content):
    pattern = re.compile(
        rf"<!-- {marker}:START -->.*?<!-- {marker}:END -->", re.S
    )
    new = f"<!-- {marker}:START -->\n{content}\n<!-- {marker}:END -->"
    return pattern.sub(new, txt)


def main():
    fetchers = {
        "PROJECTS": fetch_projects,
        "STATS": fetch_stats,
        "BLOG": fetch_blog,
    }
    results = {}
    for marker, fn in fetchers.items():
        try:
            results[marker] = fn()
        except Exception as e:  # keep other blocks intact on partial failure
            print(f"[warn] {marker} failed: {e}", flush=True)
            results[marker] = None

    files = ["README.md", "README.zh.md", "README.ja.md"]
    changed_any = False
    for f in files:
        if not os.path.exists(f):
            continue
        txt = open(f, encoding="utf-8").read()
        nt = txt
        for marker, content in results.items():
            if content is not None:
                nt = replace_block(nt, marker, content)
        if nt != txt:
            open(f, "w", encoding="utf-8").write(nt)
            changed_any = True
            print(f"updated {f}", flush=True)

    if not changed_any:
        print("no change", flush=True)


if __name__ == "__main__":
    main()
