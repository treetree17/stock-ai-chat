"""
对话服务 - 处理数据库相关操作
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import ChatHistory
from datetime import datetime

class ChatService:
    """对话管理服务"""
    
    @staticmethod
    def save_chat(
        db: Session,
        user_message: str,
        ai_response: str,
        stock_code: str = None,
        username: str = None
    ) -> ChatHistory:
        """保存对话到数据库"""
        chat = ChatHistory(
            user_message=user_message,
            ai_response=ai_response,
            stock_code=stock_code,
            username=username,
            timestamp=datetime.now()
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat

    @staticmethod
    def get_chat_history(db: Session, limit: int = 20, username: str = None) -> list:
        """获取对话历史（最近N条）"""
        query = db.query(ChatHistory)
        if username:
            query = query.filter(ChatHistory.username == username)
        chats = query.order_by(desc(ChatHistory.timestamp)).limit(limit).all()
        return list(reversed(chats))  # 倒序，显示正确顺序

    @staticmethod
    def clear_chat_history(db: Session, username: str = None):
        """清空对话历史"""
        query = db.query(ChatHistory)
        if username:
            query = query.filter(ChatHistory.username == username)
        query.delete()
        db.commit()
        db.commit()
