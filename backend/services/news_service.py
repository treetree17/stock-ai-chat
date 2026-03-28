"""
新闻服务 - 新闻缓存管理
"""

from sqlalchemy.orm import Session
from models import NewsCache

class NewsService:
    """新闻缓存服务"""
    
    @staticmethod
    def save_news(
        db: Session,
        stock_code: str,
        title: str,
        content: str = None,
        source: str = None,
        url: str = None,
        publish_date: str = None
    ) -> NewsCache:
        """保存新闻到缓存"""
        news = NewsCache(
            stock_code=stock_code,
            title=title,
            content=content,
            source=source,
            url=url,
            publish_date=publish_date
        )
        db.add(news)
        db.commit()
        db.refresh(news)
        return news
    
    @staticmethod
    def search_similar_news(db: Session, query_embedding: list, stock_code: str = None, limit: int = 3) -> list:
        """基于向量余弦相似度搜索最相关的新闻/公司资料"""
        import json
        import math

        def cosine_similarity(v1, v2):
            if not v1 or not v2 or len(v1) != len(v2): return 0.0
            dot_product = sum(a * b for a, b in zip(v1, v2))
            norm_a = math.sqrt(sum(a * a for a in v1))
            norm_b = math.sqrt(sum(b * b for b in v2))
            return dot_product / (norm_a * norm_b) if norm_a and norm_b else 0.0

        query = db.query(NewsCache).filter(NewsCache.embedding.isnot(None))
        if stock_code:
            query = query.filter(NewsCache.stock_code == stock_code)
            
        all_docs = query.all()
        
        results = []
        for doc in all_docs:
            try:
                doc_emb = json.loads(doc.embedding)
                score = cosine_similarity(query_embedding, doc_emb)
                results.append((score, doc))
            except:
                pass
                
        # 降序排序并返回Top K相关的文档
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:limit]]

    @staticmethod
    def get_news_by_stock(
        db: Session,
        stock_code: str,
        limit: int = 5
    ) -> list:
        """获取某只股票的最近新闻"""
        news_list = db.query(NewsCache)\
            .filter(NewsCache.stock_code == stock_code)\
            .order_by(NewsCache.created_at.desc())\
            .limit(limit)\
            .all()
        return news_list
    
    @staticmethod
    def update_news_cache(db: Session, stock_code: str, news_items: list):
        """批量更新新闻"""
        # 删除该股票的旧新闻
        db.query(NewsCache).filter(
            NewsCache.stock_code == stock_code
        ).delete()
        
        # 插入新新闻
        for item in news_items:
            news = NewsCache(
                stock_code=stock_code,
                title=item.get('title'),
                content=item.get('content'),
                source=item.get('source'),
                url=item.get('url'),
                publish_date=item.get('date')
            )
            db.add(news)
        
        db.commit()
