"""
轻量新闻抓取脚本（一次性运行，无定时）。
- 数据源：Google News RSS（按股票代码或关键词）
- 用法：
    cd backend
    ..\.venv\Scripts\python.exe fetch_news.py --stocks 9988.HK,0700.HK
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict
import requests
import xml.etree.ElementTree as ET

# 允许脚本直接运行时导入本地模块
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from database import SessionLocal, init_db
from models import NewsCache
from services.llm_service import LLMService

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
)


def fetch_google_news(query: str) -> List[Dict[str, str]]:
    """拉取 Google News RSS 并解析为简化结构。"""
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
    return items


def upsert_news(db, stock_code: str, items: List[Dict[str, str]]):
    """删除旧的 GoogleNews 记录后插入新数据，并生成向量。"""
    db.query(NewsCache).filter(
        NewsCache.stock_code == stock_code, NewsCache.source == "GoogleNews"
    ).delete()

    for item in items:
        text_for_embed = f"{item['title']}\n{item['content']}"
        embedding = LLMService.generate_embedding(text_for_embed)

        news = NewsCache(
            stock_code=stock_code,
            title=item["title"],
            content=item.get("content"),
            embedding=json.dumps(embedding) if embedding else None,
            source="GoogleNews",
            url=item.get("url"),
            publish_date=item.get("date") or datetime.now().strftime("%Y-%m-%d"),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        db.add(news)

    db.commit()


def main():
    parser = argparse.ArgumentParser(description="Fetch news and store embeddings")
    parser.add_argument(
        "--stocks",
        default="9988.HK,0700.HK",
        help="逗号分隔的股票代码/关键词，按此搜索 Google News",
    )
    args = parser.parse_args()

    stocks = [s.strip() for s in args.stocks.split(",") if s.strip()]
    if not stocks:
        print("⚠️ 未提供 stocks，退出")
        return

    init_db()
    db = SessionLocal()

    for code in stocks:
        try:
            print(f"⏳ 拉取 {code} 新闻...")
            items = fetch_google_news(code)
            if not items:
                print(f"⚠️ {code} 未获取到新闻")
                continue
            upsert_news(db, code, items[:10])  # 控制数量
            print(f"✅ {code} 已写入 {min(len(items),10)} 条新闻")
        except Exception as e:
            print(f"❌ {code} 抓取失败: {e}")

    db.close()


if __name__ == "__main__":
    main()
