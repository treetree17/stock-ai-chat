"""
轻量实时新闻拉取（不入库），使用 Google News RSS。
"""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import List, Dict, Union, Optional

# 同时覆盖中文和英文区域，提升港股/中概股命中率
GOOGLE_NEWS_RSS_ENDPOINTS = [
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "https://news.google.com/rss/search?q={query}&hl=zh-HK&gl=HK&ceid=HK:zh-Hant",
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
]


class LiveNewsService:
    TRUSTED_SOURCE_HINTS = [
        "reuters", "bloomberg", "wsj", "financial times", "ft",
        "cnbc", "yahoo finance", "华尔街见闻", "财联社", "第一财经",
        "新浪财经", "证券时报", "智通财经", "东方财富", "财新",
    ]

    LOW_QUALITY_SOURCE_HINTS = [
        "forum", "reddit", "stocktwits", "message board",
        "股吧", "论坛", "社区", "问答",
    ]

    @staticmethod
    def _parse_pub_ts(pub_date: str) -> float:
        if not pub_date:
            return 0.0
        try:
            dt = parsedate_to_datetime(pub_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return 0.0

    @staticmethod
    def _clean_text(text: str) -> str:
        return " ".join(unescape(text or "").lower().split())

    @staticmethod
    def _extract_source_hint(title: str) -> str:
        t = (title or "").strip()
        # Google News RSS 标题常见格式："headline - source"
        if " - " in t:
            return t.rsplit(" - ", 1)[-1].strip().lower()
        return ""

    @staticmethod
    def _is_garbled_text(text: str) -> bool:
        s = (text or "").strip()
        if not s:
            return True

        if "\ufffd" in s:
            return True

        total = len(s)
        if total == 0:
            return True

        def is_cjk(ch: str) -> bool:
            code = ord(ch)
            return 0x4E00 <= code <= 0x9FFF

        valid = 0
        for ch in s:
            if ch.isascii() or is_cjk(ch):
                valid += 1

        # 若可读字符比例过低，判定为乱码
        return (valid / total) < 0.55

    @staticmethod
    def _score_item(item: Dict[str, str], terms: List[str]) -> int:
        title = LiveNewsService._clean_text(item.get("title", ""))
        content = LiveNewsService._clean_text(item.get("content", ""))
        source_hint = LiveNewsService._extract_source_hint(item.get("title", ""))
        score = 0
        for term in terms:
            t = (term or "").strip().lower()
            if not t:
                continue
            if t in title:
                score += 3
            if t in content:
                score += 1

        if source_hint:
            if any(h in source_hint for h in LiveNewsService.TRUSTED_SOURCE_HINTS):
                score += 2
            if any(h in source_hint for h in LiveNewsService.LOW_QUALITY_SOURCE_HINTS):
                score -= 2

        return score

    @staticmethod
    def _fetch_yahoo_symbol_news(symbol: str, limit: int = 5) -> List[Dict[str, str]]:
        # 代码级新闻兜底，避免仅靠关键词命中
        rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={requests.utils.quote(symbol)}&region=US&lang=en-US"
        try:
            resp = requests.get(rss_url, timeout=10)
            resp.raise_for_status()
            xml_text = resp.content.decode("utf-8", errors="ignore")
            root = ET.fromstring(xml_text)
        except Exception:
            return []

        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "content": desc,
                    "_ts": LiveNewsService._parse_pub_ts(pub_date),
                }
            )
            if len(items) >= limit:
                break
        return items

    @staticmethod
    def fetch(
        query: Union[str, list],
        limit: int = 5,
        terms: Optional[List[str]] = None,
        stock_code: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        queries = query if isinstance(query, list) else [query]
        queries = [q.strip() for q in queries if q and q.strip()]
        if not queries:
            return []

        items = []
        seen = set()

        for q in queries:
            for endpoint in GOOGLE_NEWS_RSS_ENDPOINTS:
                url = endpoint.format(query=requests.utils.quote(q))
                try:
                    resp = requests.get(url, timeout=10)
                    resp.raise_for_status()
                    xml_text = resp.content.decode("utf-8", errors="ignore")
                    root = ET.fromstring(xml_text)
                except Exception as e:
                    print(f"Error fetching live news: {e}")
                    continue

                for item in root.findall(".//item"):
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    pub_date = (item.findtext("pubDate") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    if not title or not link:
                        continue
                    if LiveNewsService._is_garbled_text(title):
                        continue

                    key = (title.lower(), link)
                    if key in seen:
                        continue
                    seen.add(key)

                    items.append(
                        {
                            "title": title,
                            "url": link,
                            "date": pub_date,
                            "content": desc,
                            "_ts": LiveNewsService._parse_pub_ts(pub_date),
                        }
                    )

        if stock_code:
            items.extend(LiveNewsService._fetch_yahoo_symbol_news(stock_code, limit=limit))

        # 相关性打分，优先保留与股票/公司强相关的条目
        score_terms = [t for t in (terms or []) if t]
        if not score_terms:
            # 无外部terms时，从query中提取基础词，避免全0分导致无关新闻混入
            for q in queries:
                parts = [p.strip().lower() for p in q.replace("/", " ").replace("-", " ").split()]
                for p in parts:
                    if len(p) >= 2:
                        score_terms.append(p)
        if stock_code:
            score_terms.extend([stock_code, stock_code.split(".")[0]])
        scored = []
        for item in items:
            score = LiveNewsService._score_item(item, score_terms)
            item["_score"] = score
            scored.append(item)

        # 当存在近期新闻时，主动抑制过旧新闻混入，避免分析被旧事实污染
        now_ts = datetime.now(timezone.utc).timestamp()
        has_recent = any((now_ts - x.get("_ts", 0.0)) <= 30 * 86400 for x in scored if x.get("_ts", 0.0) > 0)
        if has_recent:
            scored = [x for x in scored if x.get("_ts", 0.0) <= 0 or (now_ts - x.get("_ts", 0.0)) <= 60 * 86400]

        # 如果有相关命中，则只保留相关项；否则回退到按时间排序
        related_items = [x for x in scored if x.get("_score", 0) > 0]
        final_items = related_items if related_items else scored

        # 按发布时间降序排序，优先使用最近新闻 (时间权重放大)
        final_items.sort(key=lambda x: (x.get("_score", 0), x.get("_ts", 0.0)), reverse=True)
        for item in final_items:
            item.pop("_ts", None)
            item.pop("_score", None)
        return final_items[:limit]
