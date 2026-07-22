#!/usr/bin/env python3
"""通过 GitHub Contents API 上传所有文件,保留 auto_init 的 initial commit。

这样不会破坏 GitHub 的 profile README 标记(避免 force push 问题)。
"""
import base64
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ["GH_TOKEN"]
OWNER = "weed33834"
REPO = "weed33834"
API = f"https://api.github.com/repos/{OWNER}/{REPO}/contents"

FILES = [
    ("README.md", "feat: badhope/weed33834 profile README 星空主题"),
    (".gitignore", "chore: add gitignore"),
    ("assets/banner.svg", "feat: add starry banner svg"),
    ("assets/divider.svg", "feat: add divider svg"),
    ("assets/quote.svg", "chore: 每日一言(hitokoto.cn)"),
    ("assets/onthisday.svg", "chore: 历史上的今天(Wikipedia)"),
    ("scripts/gen_assets.py", "feat: add asset generation script"),
    (".github/workflows/daily-refresh.yml", "feat: add daily refresh workflow"),
]


def api_call(method, path, payload=None):
    url = f"{API}/{path}" if path else API
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
            return r.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:200]}


def get_file_sha(path):
    """获取远端文件的 sha(更新时需要)。不存在返回 None。"""
    status, data = api_call("GET", path)
    if status == 200 and isinstance(data, dict):
        return data.get("sha")
    return None


def upload_file(local_path, remote_path, message):
    """上传单个文件。若远端已存在,需提供 sha 才能更新。"""
    content = (ROOT / local_path).read_bytes()
    b64 = base64.b64encode(content).decode("ascii")
    sha = get_file_sha(remote_path)
    payload = {"message": message, "content": b64, "branch": "main"}
    if sha:
        payload["sha"] = sha
    status, data = api_call("PUT", remote_path, payload)
    action = "updated" if sha else "created"
    ok = status in (200, 201)
    print(f"  [{'OK' if ok else 'FAIL'}] {remote_path} ({action}, HTTP {status})")
    if not ok:
        print(f"       {str(data)[:200]}")
    return ok


def main():
    print(f"上传 {len(FILES)} 个文件到 {OWNER}/{REPO} via Contents API...")
    ok_count = 0
    for local, msg in FILES:
        remote = local
        if upload_file(local, remote, msg):
            ok_count += 1
    print(f"\n完成: {ok_count}/{len(FILES)} 成功")


if __name__ == "__main__":
    main()
