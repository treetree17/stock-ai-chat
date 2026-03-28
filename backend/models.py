"""
SQLAlchemy ORM模型定义
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class User(Base):
    """用户表"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class ChatHistory(Base):
    """对话History表"""
    __tablename__ = 'chat_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=True)       # 所属用户名
    user_message = Column(Text, nullable=False)        # 用户问题
    ai_response = Column(Text, nullable=False)         # AI回答
    stock_code = Column(String(20))                    # 涉及的股票代码
    timestamp = Column(DateTime, default=datetime.now) # 创建时间
    
    def __repr__(self):
        return f"<ChatHistory(id={self.id}, stock={self.stock_code})>"

class NewsCache(Base):
    """新闻缓存表"""
    __tablename__ = 'news_cache'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    title = Column(Text, nullable=False)               # 新闻标题
    content = Column(Text)                             # 新闻内容摘要
    embedding = Column(Text, nullable=True)            # ！！！RAG新增：文本向量 (JSON字符串)
    source = Column(String(50))                        # 来源（新浪、网易等）
    url = Column(Text)                                 # 新闻链接
    publish_date = Column(String(20))                  # 发布日期
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now)
    
    def __repr__(self):
        return f"<NewsCache(id={self.id}, stock={self.stock_code}, title={self.title[:30]})>"

