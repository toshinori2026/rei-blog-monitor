
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BLOG_URL = "https://ske48.co.jp/blog/list/92/96/"
STATE_FILE = Path("seen.json")
NTFY_TOPIC = os.environ["NTFY_TOPIC"]

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0"
})

# ブログ一覧を取得
response = session.get(BLOG_URL, timeout=30)
response.raise_for_status()

soup = BeautifulSoup(response.text, "html.parser")
articles = {}

for a in soup.select("a[href]"):
    link = urljoin(BLOG_URL, a["href"])
    parsed = urlparse(link)

    if parsed.netloc != "ske48.co.jp":
        continue

    match = re.search(
        r"/blog/detail/(\d+)/?$", parsed.path
    )
    if not match:
        continue

    article_id = match.group(1)
    title = a.get_text(" ", strip=True)

    articles[article_id] = {
        "title": title or "新しいブログ",
        "url": link
    }

if not articles:
    raise RuntimeError(
        "記事が取得できませんでした。"
        "ブログのHTML構造を確認してください。"
    )

current_ids = set(articles)

# 初回は既存記事を記録するだけ
if not STATE_FILE.exists():
    STATE_FILE.write_text(
        json.dumps(sorted(current_ids)),
        encoding="utf-8"
    )
    print(f"初回登録: {len(current_ids)}件")
    raise SystemExit(0)

seen = set(json.loads(
    STATE_FILE.read_text(encoding="utf-8")
))

new_ids = sorted(current_ids - seen, key=int)

for article_id in new_ids:
    article = articles[article_id]
    title = article["title"]
    posted = "日時不明"

    detail = session.get(article["url"], timeout=30)
    detail.raise_for_status()
    page = BeautifulSoup(detail.text, "html.parser")

    heading = page.select_one("h1")
    if heading:
        title = heading.get_text(" ", strip=True) or title

    date_match = re.search(
        r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}"
        r"(?:\s+\d{1,2}:\d{2})?",
        page.get_text(" ", strip=True)
    )
    if date_match:
        posted = date_match.group(0)

    message = (
        f"{title}\n"
        f"投稿日時: {posted}\n"
        f"{article['url']}"
    )

    result = session.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={
            "Title": "Rei Blog New Post",
            "Click": article["url"],
            "Tags": "tada"
        },
        timeout=30
    )
    result.raise_for_status()

    print(f"新着通知: {article['url']}")

    # 通知済み記事を記録
    seen.add(article_id)
    STATE_FILE.write_text(
        json.dumps(sorted(seen)),
        encoding="utf-8"
    )

print(f"確認完了: 新着{len(new_ids)}件")
