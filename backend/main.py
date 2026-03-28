"""
FastAPI主程序 - 股票AI助手
"""

from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv
import os
import asyncio
import json
import hashlib

# 强制使用 HuggingFace 国内镜像源，解决下载预训练模型报错
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

# 导入数据库和服务
from database import init_db, get_db
from models import User
from services.chat_service import ChatService
from services.news_service import NewsService
from services.live_news_service import LiveNewsService
from services.market_data_service import MarketDataService
from services.llm_service import LLMService
from services.cache import CacheService

load_dotenv()

# 初始化FastAPI
app = FastAPI(
    title="Stock AI Assistant",
    description="LLM-based Intelligent Stock Analyst Assistant",
    version="1.0.0"
)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 数据模型
class ChatRequest(BaseModel):
    message: str
    stock_code: str = None

class ChatResponse(BaseModel):
    response: str
    stock_code: str = None
    timestamp: str
    chart_options: str = None

class LoginRequest(BaseModel):
    username: str
    password: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# 应用启动时初始化数据库
@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    init_db()
    print("✅ App started successfully! Visit http://localhost:8000/docs for API docs")

# API端点：注册
@app.post("/api/register")
async def register(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    new_user = User(username=request.username, password=hash_password(request.password))
    db.add(new_user)
    db.commit()
    return {"success": True, "message": "Registration successful, please login"}

# API端点：登录
@app.post("/api/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user:
        raise HTTPException(status_code=400, detail="User does not exist")
    if user.password != hash_password(request.password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    return {"success": True, "token": user.username, "username": user.username, "message": "Login successful"}

# API端点1：聊天
@app.post("/api/chat")
async def chat(request: ChatRequest, x_username: str = Header(None), db: Session = Depends(get_db)):
    """
    聊天API - 流式返回
    """
    # 极简身份校验
    if not x_username:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing token, please login first")

    async def event_generator():
        try:
            yield f'data: {json.dumps({"type": "status", "message": "🔍 Analyzing intent and stock code..."})}\n\n'
            
            # 意图判断与兜底过滤
            msg_lower = request.message.lower()
            msg_clean_words = "".join(c if c.isalnum() else ' ' for c in msg_lower).split()
            
            # 扩展金融关键词库
            financial_keywords = [
                "news", "market", "trend", "price", "up", "down", "buy", "sell", 
                "analyze", "report", "economy", "capital", "sector", "valuation", 
                "stock", "company", "dividend", "shares", "portfolio", "invest",
                "市场", "趋势", "价格", "涨", "跌", "买停", "买入", "卖出", "分析",
                "报告", "经济", "资本", "板块", "估值", "股票", "公司", "分红",
                "大盘", "指数", "财报", "投资", "收益", "走势", "行情"
            ]
            
            # 中英文闲聊检测语料库 (要求全词匹配或者直接相等)
            greetings = [
                "hi", "hello", "hey", "how are you", "good morning", "good evening", "who are you",
                "你好", "在吗", "早上好", "晚上好", "你是谁", "你能做什么", "哈喽", "喂"
            ]
            
            # 强化型闲聊判断：如果在纯字母情况下，字数<=5且匹配到greetings，则绝对是闲聊
            is_english_greeting = msg_lower.isascii() and (len(msg_clean_words) <= 5) and any(g in msg_lower for g in greetings)
            is_chinese_greeting = (not msg_lower.isascii()) and (len(msg_lower) <= 8) and any(g in msg_lower for g in greetings)
            is_strict_greeting = is_english_greeting or is_chinese_greeting
            
            # 如果是闲聊，强制清空 stock_code，防止误判 "hello" 为股票代码
            if is_strict_greeting:
                stock_code = None
            else:
                stock_code = request.stock_code or MarketDataService.extract_stock_code(request.message)
            
            has_stock = bool(stock_code)
            stock_code = stock_code or "N/A"
            
            if is_strict_greeting:
                needs_api = False
            elif has_stock:
                needs_api = True
            else:
                # 模糊匹配中英文金融关键词
                needs_api = any(kw in msg_lower for kw in financial_keywords)

            if needs_api:
                yield f'data: {json.dumps({"type": "status", "message": "📡 Fetching live multi-source data (Market, News, Reports)..."})}\n\n'
                
                search_query = f"{request.message} {stock_code} stock OR report OR financial" if has_stock else request.message
                
                # 使用 asyncio.gather 并发执行 IO 密集型操作
                async def get_stock():
                    return await asyncio.to_thread(MarketDataService.get_stock_data, stock_code) if has_stock else {}
                
                async def get_kline():
                    return await asyncio.to_thread(MarketDataService.get_kline_options, stock_code) if has_stock else None
                
                async def get_live_news():
                    try:
                        return await asyncio.to_thread(LiveNewsService.fetch, search_query, 3)
                    except Exception as e:
                        print(f"⚠️ Failed to fetch live news: {e}")
                        return []
                        
                async def get_embedding():
                    return await asyncio.to_thread(LLMService.generate_embedding, request.message)

                # 并发获取
                stock_data, chart_options_str, live_news_items, query_embedding = await asyncio.gather(
                    get_stock(), get_kline(), get_live_news(), get_embedding()
                )
                
                if chart_options_str:
                    yield f'data: {json.dumps({"type": "chart", "options": chart_options_str})}\n\n'
                
                live_news_text = format_live_news(live_news_items)
                
                if query_embedding:
                    news_list = await asyncio.to_thread(NewsService.search_similar_news, db, query_embedding, stock_code if has_stock else None, 2)
                else:
                    news_list = await asyncio.to_thread(NewsService.get_news_by_stock, db, stock_code, 2) if has_stock else []
                    
                db_news_text = format_news(news_list)
                news_text = f"[Live Real-time News]\n{live_news_text if live_news_text else 'No recent live news'}\n[Recent Historical News Match]\n{db_news_text}"
                
            else:
                stock_data = {}
                chart_options_str = None
                news_text = ""
            
            yield f'data: {json.dumps({"type": "status", "message": "🧠 AI is reasoning..."})}\n\n'

            # 获取最近几条对话历史组合到上下文
            history_chats = ChatService.get_chat_history(db, limit=3, username=x_username)
            history_text = "\n".join([f"User: {c.user_message}\nAI: {c.ai_response}" for c in history_chats])
            
            # 构建Prompt
            if has_stock:
                price_info = f"- **Current Price**: {stock_data.get('price', 'Unknown')} USD\n- **Today Change**: {stock_data.get('change', 'Unknown')}%\n- **Volume**: {stock_data.get('volume', 'Unknown')}" if stock_data else "Currently unable to get latest market data for this stock."

                prompt = f"""You are a professional AI stock analyst. Generate an in-depth analytical response directly without any formal greetings, filler introductions (like "As a senior analyst", "Here is your analysis", etc) or self-introductions. Start right away with the core analysis.

### Chat History Context
{history_text if history_text else "No chat history"}

**User Message**: {request.message}

### Current Market Data ({stock_code})
{price_info}

### Recent Core News
{news_text if news_text else 'No latest related news'}

**Answering Principles**:
1. **Strict Fact Anchoring (Anti-Hallucination)**: If the provided news and market data have absolutely NO information about the requested company, you MUST reply: "Sorry, the system could not retrieve relevant financial data or reports for this company at this time." DO NOT guess or generalize!
2. **In-depth Analysis**: If data exists, provide a comprehensive breakdown including "Fundamentals/Market Interpretation", "Core News Deep Dive", and "Market Outlook".
3. **News Authenticity**: When citing news, strictly use the provided [Recent Core News] and include the `[News Link](URL)`.
4. **Language Matching**: You MUST reply in the exact same language as the **User Message**. If the user asks in English, your ENTIRE response MUST be in English. No Chinese characters allowed if the user asks in English!
5. **No Roleplaying Introductions**: Do not say "As an analyst...", "I'm delighted to provide...". Provide ONLY the requested analysis immediately.
6. **Disclaimer**: At the very end of any stock analysis, you must include this italicized text: *⚠️ AI deep analysis is for reference only, the market is highly volatile, and this does not constitute substantive investment advice.*"""

            elif needs_api:
                prompt = f"""You are an intelligent AI assistant. Please answer the following questions in detail using Markdown format.

### Chat History Context
{history_text if history_text else "No chat history"}

**User Message**: {request.message}

### Reference News
{news_text if news_text else 'None'}

**Requirements**:
1. **Identify General vs Specific Domain Questions**: If the user asks general knowledge questions, ignore the financial context and answer accurately as a general-purpose AI.
2. If it is a macro-market or industry question, objectively answer based on provided news and your own knowledge.
3. **Language Matching**: You MUST reply in the exact same language as the **User Message**. If the user asks in English, your ENTIRE response MUST be in English.
4. If it is a finance question but no relevant news is found, explicitly state "No specific related news found currently", then answer based on existing knowledge, and conclude with: *Analysis is for reference only, not investment advice.*"""

            else:
                prompt = f"""You are a smart and friendly AI assistant. The user's current question is not related to a specific stock.
Answer casually, comprehensively, and helpfully as a general-purpose LLM.
Do not force connections to stock data or financial jargon.

**Language Matching**: You MUST reply in the exact same language as the **User Message**. If the user asks in English, your ENTIRE response MUST be in English.

**User Message**: {request.message}"""
            
            # 流式生成回到
            ai_response = ""
            for chunk in LLMService.generate_stream(prompt):
                ai_response += chunk
                yield f'data: {json.dumps({"type": "chunk", "content": chunk})}\n\n'
                await asyncio.sleep(0)
            
            # 保存到数据库
            from database import SessionLocal
            with SessionLocal() as db_session:
                ChatService.save_chat(
                    db_session,
                    user_message=request.message,
                    ai_response=ai_response,
                    stock_code=stock_code,
                    username=x_username
                )

            yield f'data: {json.dumps({"type": "done"})}\n\n'

        except Exception as e:
            yield f'data: {json.dumps({"type": "error", "message": str(e)})}\n\n'
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")

# API端点2：获取对话历史
@app.get("/api/history")
async def get_history(limit: int = 20, x_username: str = Header(None), db: Session = Depends(get_db)):
    """获取最近的对话历史"""
    if not x_username:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing token, please login first")
        
    chats = ChatService.get_chat_history(db, limit, username=x_username)
    return {
        "total": len(chats),
        "chats": [
            {
                "user": c.user_message,
                "ai": c.ai_response,
                "stock": c.stock_code,
                "time": c.timestamp.isoformat()
            }
            for c in chats
        ]
    }

# API端点3：清空对话历史
@app.post("/api/history/clear")
async def clear_history(x_username: str = Header(None), db: Session = Depends(get_db)):
    if not x_username:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing token, please login first")
    ChatService.clear_chat_history(db, username=x_username)
    return {"message": "Chat history cleared"}

# API端点：实时news（不入库）
@app.get("/api/news/live")
async def get_live_news(q: str, limit: int = 5):
    """按关键词即时抓取news（不落库）。"""
    try:
        items = LiveNewsService.fetch(q, limit=limit)
        return {"total": len(items), "items": items}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# API端点4：清空对话历史
@app.delete("/api/history")
async def clear_history(db: Session = Depends(get_db)):
    """清空所有对话历史"""
    ChatService.clear_chat_history(db)
    return {"status": "success", "message": "All chat histories cleared"}

# API端点5：健康检查
@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """健康检查"""
    return {
        "status": "ok",
        "database": "connected",
        "timestamp": datetime.now().isoformat()
    }

# 工具函数
def format_news(news_list) -> str:
    """格式化数据库news列表"""
    if not news_list:
        return ""
    
    news_text = ""
    for i, news in enumerate(news_list, 1):
        # 尝试检查news对象里是否有 url 和 summary/content
        url_part = f" [Original Link]({news.url})" if hasattr(news, 'url') and news.url else ""
        content_part = getattr(news, 'content', getattr(news, 'summary', ''))
        
        # 截取一部分内容展示作为详情，防止全塞进prompt太长，但给模型一定的细节
        details = f"\n  > Details: {content_part[:150]}..." if content_part else ""
        
        news_text += f"{i}. **{news.title}** ({news.publish_date}){url_part}{details}\n\n"
    
    return news_text

def format_live_news(items: list) -> str:
    """格式化实时抓取的news字典列表"""
    import re
    if not items:
        return ""
        
    text = ""
    for i, item in enumerate(items, 1):
        title = item.get("title", "No Title")
        link = item.get("url")  # 修复字段名映射
        pub_date = item.get("date", "Just now")
        # 清理Google RSS返回的HTML标签内容
        desc_raw = item.get("content", "")
        desc_clean = re.sub(r'<[^>]+>', '', desc_raw).replace('&nbsp;', ' ').strip()
        
        url_part = f" [Original Link]({link})" if link else ""
        details = f"\n  > Details: {desc_clean[:150]}..." if desc_clean else ""
        
        text += f"{i}. (Breaking Today) **{title}** ({pub_date}){url_part}{details}\n\n"
    return text

# 挂载前端静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    
    @app.get("/")
    async def serve_frontend():
        return FileResponse(os.path.join(frontend_dir, "index.html"))

    @app.get("/{path:path}")
    async def catch_all_fallback(path: str):
        # 兼容一些前端可能存在的静态文件直接访问路径，排除 api 前缀
        if not path.startswith("api/"):
            file_path = os.path.join(frontend_dir, path)
            if os.path.exists(file_path):
                return FileResponse(file_path)
            # 默认返回 index.html
            return FileResponse(os.path.join(frontend_dir, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
