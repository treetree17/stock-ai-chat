"""
轻量实时新闻拉取（不入库），使用 Google News RSS。
"""

import requests
import xml.etree.ElementTree as ET
from typing import List, Dict

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
)


class LiveNewsService:
    @staticmethod
    def fetch(query: str, limit: int = 5) -> List[Dict[str, str]]:
        url = GOOGLE_NEWS_RSS.format(query=requests.utils.quote(query))
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)
        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "content": desc,
                }
            )
            if len(items) >= limit:
                break
        return items
