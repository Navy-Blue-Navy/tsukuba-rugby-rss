import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from email.utils import format_datetime, parsedate_to_datetime
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET
import hashlib
import os
import re
import time

BASE_URL = "https://www.tsukubaowls.com"
CATEGORY_URL = BASE_URL + "/news/categories/rugby"
OUTPUT = "tsukuba_rugby.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def make_guid(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def get_old_items():
    old = {}

    if not os.path.exists(OUTPUT):
        return old

    try:
        root = ET.parse(OUTPUT).getroot()

        for item in root.findall("./channel/item"):
            guid = item.findtext("guid")

            if guid:
                old[guid] = {
                    "title": item.findtext("title") or "",
                    "link": item.findtext("link") or "",
                    "description": item.findtext("description") or "",
                    "pubDate": item.findtext("pubDate") or "",
                }
    except Exception:
        pass

    return old


def parse_display_date(text, now):
    # YYYY年M月D日
    m = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
        text
    )

    if m:
        year, month, day = map(int, m.groups())

        return datetime(
            year, month, day, 12, 0, 0,
            tzinfo=JST
        )

    # M月D日
    m = re.search(
        r"(?<!\d)(\d{1,2})月(\d{1,2})日",
        text
    )

    if m:
        month, day = map(int, m.groups())
        year = now.year

        dt = datetime(
            year, month, day, 12, 0, 0,
            tzinfo=JST
        )

        # 年末年始対策
        if dt > now + timedelta(days=30):
            dt = datetime(
                year - 1, month, day,
                12, 0, 0,
                tzinfo=JST
            )

        return dt

    # 「2日前」など
    m = re.search(r"(\d+)\s*日前", text)

    if m:
        days = int(m.group(1))

        d = now - timedelta(days=days)

        return datetime(
            d.year, d.month, d.day,
            12, 0, 0,
            tzinfo=JST
        )

    # 今日
    if "今日" in text:
        return datetime(
            now.year, now.month, now.day,
            12, 0, 0,
            tzinfo=JST
        )

    # 昨日
    if "昨日" in text:
        d = now - timedelta(days=1)

        return datetime(
            d.year, d.month, d.day,
            12, 0, 0,
            tzinfo=JST
        )

    return None


now = datetime.now(JST)

items = []
seen = set()

# ラグビー部は現在複数ページあるため順番に取得
for page in range(1, 20):

    if page == 1:
        page_url = CATEGORY_URL
    else:
        page_url = f"{CATEGORY_URL}/page/{page}"

    response = requests.get(
        page_url,
        headers=HEADERS,
        timeout=30
    )

    print(
        f"ページ {page} HTTP:",
        response.status_code
    )

    if response.status_code == 404:
        break

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    page_count = 0

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")
        article_url = urljoin(
            BASE_URL,
            href
        )

        # 個別記事は /post/
        if "/post/" not in article_url:
            continue

        if article_url in seen:
            continue

        title = " ".join(
            a.stripped_strings
        ).strip()

        if not title:
            continue

        # 画像リンク等を避けるため、
        # 記事カード全体から情報を確認
        parent = a
        card_text = ""

        for _ in range(8):
            if parent is None:
                break

            text = " ".join(
                parent.stripped_strings
            )

            if "ラグビー部" in text:
                card_text = text
                break

            parent = parent.parent

        if not card_text:
            continue

        dt = parse_display_date(
            card_text,
            now
        )

        if not dt:
            continue

        seen.add(article_url)

        items.append({
            "title": title,
            "link": article_url,
            "description":
                "筑波大学 体育スポーツ局 ラグビー部",
            "pubDate": format_datetime(dt),
            "guid": make_guid(article_url),
            "sort_date": dt,
        })

        page_count += 1

    print(
        f"ページ {page} 取得:",
        page_count,
        "件"
    )

    # 記事がないページまで来たら終了
    if page_count == 0:
        break

    time.sleep(0.3)


items.sort(
    key=lambda x: x["sort_date"],
    reverse=True
)


# 既存RSSを保持
old_items = get_old_items()

all_items = dict(old_items)

for item in items:

    all_items[item["guid"]] = {
        "title": item["title"],
        "link": item["link"],
        "description": item["description"],
        "pubDate": item["pubDate"],
    }


def parse_date(value):
    try:
        return parsedate_to_datetime(value)
    except Exception:
        return datetime(
            1970, 1, 1,
            tzinfo=timezone.utc
        )


sorted_items = sorted(
    all_items.items(),
    key=lambda x:
        parse_date(x[1]["pubDate"]),
    reverse=True
)[:300]


# RSS生成
rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = (
    "筑波大学 体育スポーツ局 ラグビー部"
)

ET.SubElement(
    channel,
    "link"
).text = CATEGORY_URL

ET.SubElement(
    channel,
    "description"
).text = (
    "筑波大学 体育スポーツ局 "
    "ラグビー部の新着記事"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"


for guid, data in sorted_items:

    item = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        item,
        "title"
    ).text = data["title"]

    ET.SubElement(
        item,
        "link"
    ).text = data["link"]

    ET.SubElement(
        item,
        "description"
    ).text = data["description"]

    ET.SubElement(
        item,
        "pubDate"
    ).text = data["pubDate"]

    guid_el = ET.SubElement(
        item,
        "guid",
        isPermaLink="false"
    )

    guid_el.text = guid


tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


print()
print("RSS作成成功")
print(
    "今回取得:",
    len(items),
    "件"
)
print(
    "RSS保存件数:",
    len(sorted_items),
    "件"
)
print(
    "保存先:",
    os.path.abspath(OUTPUT)
)

print()
print("取得記事:")

for i, item in enumerate(items, 1):

    print()
    print(
        f"[{i}] {item['title']}"
    )
    print(
        "    ",
        item["pubDate"]
    )
    print(
        "    ",
        item["link"]
    )