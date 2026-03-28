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
import re

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
from alias_config import COMPANY_ALIASES

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

# --- fastapi logic overrides ---
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
            live_news_items = []
            news_list = []
            source_entries = []
            source_evidence_text = "None"
            yield f'data: {json.dumps({"type": "status", "message": "🔍 Analyzing intent and stock code..."})}\n\n'

            # 意图判断与兜底过滤
            msg_lower = request.message.lower()
            msg_clean_words = "".join(c if c.isalnum() else ' ' for c in msg_lower).split()

            def detect_text_language(text: str) -> str:
                """粗粒度语言检测，仅用于约束回复模板语言。"""
                sample = text or ""
                has_cn = bool(re.search(r"[\u4e00-\u9fff]", sample))
                has_en = bool(re.search(r"[A-Za-z]", sample))
                if has_en and not has_cn:
                    return "en"
                if has_cn and not has_en:
                    return "zh"
                if has_en and has_cn:
                    en_tokens = len(re.findall(r"[A-Za-z]+", sample))
                    cn_chars = len(re.findall(r"[\u4e00-\u9fff]", sample))
                    return "en" if en_tokens >= cn_chars else "zh"
                return "en"

            response_lang = detect_text_language(request.message)
            lang_is_en = response_lang == "en"
            
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
                "hi", "hello", "hey", "how are you", "good morning", "good evening", "who are you","what can you do", "greetings", "hiya", "yo", "sup","whats up", "are you there", "你好", "您好",
                "你好", "在吗", "早上好", "晚上好", "你是谁", "你能做什么", "哈喽", "喂", "嗨", "您好", "请问一下", "请帮我", "谢谢", "感谢", "再见", "拜拜", "see you", "goodbye", "thanks", "thank you", "thx", "tnx"
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

            def build_news_queries(user_msg: str, code: str = None) -> list:
                clean_msg = re.sub(r"\s+", " ", user_msg or "").strip()
                clean_cn_msg = re.sub(r"[^\w\u4e00-\u9fa5\s\.\-]", " ", clean_msg)
                clean_cn_msg = re.sub(r"\s+", " ", clean_cn_msg).strip()
                stopwords = {
                    "给我", "请", "帮我", "一下", "股票", "信息", "股票信息", "股价", "走势", "分析", "公司", "最新"
                }
                cn_terms = [t for t in re.findall(r"[\u4e00-\u9fa5]{2,8}", clean_cn_msg) if t not in stopwords]
                en_terms = [t for t in re.findall(r"[A-Za-z][A-Za-z\-\.]{2,20}", clean_msg) if t.lower() not in {"stock", "news", "analysis"}]

                if cn_terms:
                    base_msg = max(cn_terms, key=len)
                elif en_terms:
                    base_msg = max(en_terms, key=len)
                else:
                    base_msg = clean_cn_msg or clean_msg or "stock news"

                queries = []
                if code and code != "N/A":
                    code_plain = code.split(".")[0]
                    queries.extend([
                        f"{base_msg} {code} news when:7d",                     # 优先全网宽泛抓取（Google News核心匹配）
                        f"{base_msg} {code} 财报 评级 公告 业务 when:14d",          # 业务基本面
                        f"{base_msg} {code} site:finance.eastmoney.com when:7d", # 其次选东方财富等垂直财经网站
                        f"{base_msg} {code_plain} 港股 新闻 研报 when:7d",
                        f"{base_msg} {code} site:finance.sina.com.cn when:7d",   # 最后选择新浪财经
                        f"{base_msg} {code} earnings guidance rating when:14d",
                    ])
                else:
                    queries.extend([
                        f"{base_msg} 财经 新闻 when:7d",
                        f"{base_msg} market analysis when:7d",
                    ])

                # 去重并限制数量，避免RSS请求过多
                seen = set()
                deduped = []
                for q in queries:
                    if q not in seen:
                        seen.add(q)
                        deduped.append(q)
                return deduped[:6]

            def build_news_terms(user_msg: str, code: str = None) -> list:
                terms = []
                raw = user_msg or ""
                stopwords = {
                    "给我", "请", "帮我", "一下", "股票", "信息", "股票信息", "股价", "走势", "分析", "公司", "最新"
                }
                cn_terms = re.findall(r"[\u4e00-\u9fa5]{2,8}", raw)
                en_terms = re.findall(r"[A-Za-z][A-Za-z\-\.]{2,20}", raw)

                terms.extend([t for t in cn_terms if t not in stopwords][:8])
                terms.extend([t.lower() for t in en_terms if t.lower() not in {"stock", "news", "analysis"}][:8])

                if code and code != "N/A":
                    terms.extend([code, code.split(".")[0]])

                # 去重
                uniq = []
                seen = set()
                for t in terms:
                    k = (t or "").strip().lower()
                    if not k or k in seen:
                        continue
                    seen.add(k)
                    uniq.append(t)
                return uniq[:20]

            def build_source_entries(live_items: list, db_items: list, max_sources: int = 10) -> list:
                entries = []
                seen_urls = set()
                url_extract_pattern = re.compile(r"https?://[^\s\])>\"']+")

                def add_entry(title: str, date: str, url: str, snippet: str = ""):
                    if not url:
                        return
                    clean_url = url.strip().rstrip('.,;')
                    if not clean_url or clean_url in seen_urls:
                        return
                    seen_urls.add(clean_url)
                    entries.append(
                        {
                            "title": (title or "Reference Source").strip()[:120],
                            "date": (date or "N/A").strip()[:80],
                            "url": clean_url,
                            "snippet": re.sub(r"\s+", " ", (snippet or "")).strip()[:180],
                        }
                    )

                for item in live_items:
                    title = item.get("title") or "Live News"
                    date = item.get("date") or "N/A"
                    content = item.get("content", "") or ""
                    add_entry(title, date, item.get("url"), content)
                    for extracted in url_extract_pattern.findall(content):
                        add_entry(title, date, extracted, content)

                for item in db_items:
                    title = getattr(item, "title", "Historical News")
                    date = str(getattr(item, "publish_date", "N/A") or "N/A")
                    content = getattr(item, "content", "") or ""
                    add_entry(title, date, getattr(item, "url", None), content)
                    for extracted in url_extract_pattern.findall(content):
                        add_entry(title, date, extracted, content)

                return entries[:max_sources]

            def build_source_evidence(entries: list, max_items: int = 6) -> str:
                if not entries:
                    return "None"
                lines = []
                for idx, entry in enumerate(entries[:max_items], 1):
                    snippet = entry.get("snippet") or "No snippet"
                    lines.append(f"[S{idx}] {entry['title']} | {entry['date']} | {snippet}")
                return "\n".join(lines)

            def build_company_alias_terms(code: str, user_msg: str = "") -> list:
                terms = []
                msg = (user_msg or "").lower()
                code_norm = (code or "").upper()
                if code_norm and code_norm != "N/A":
                    terms.extend([code_norm.lower(), code_norm.split(".")[0].lower()])
                code_prefix = code_norm.split(".")[0] if code_norm and code_norm != "N/A" else ""

                # Automatically extract plain names from user_msg to feed into terms 
                # to catch generic things like "XX集团" or "XX股份"
                if msg:
                    cn_words = re.findall(r"[\u4e00-\u9fa5]{2,6}", msg)
                    for w in cn_words:
                        if w not in ["股票", "行情", "分析", "走势", "公司", "给我"]:
                            terms.append(w)
                            terms.append(f"{w}集团")
                            terms.append(f"{w}股份")

                if code_prefix in COMPANY_ALIASES:
                    terms.extend(COMPANY_ALIASES[code_prefix])

                # 动态反向匹配：如果用户消息里包含 COMPANY_ALIASES 里面的任何硬词，把对应组内所有词放入搜索池
                for code_key, alias_list in COMPANY_ALIASES.items():
                    if any(alias in msg for alias in alias_list):
                        terms.extend(alias_list)

                uniq = []
                seen = set()
                for t in terms:
                    k = (t or "").strip().lower()
                    if not k or k in seen:
                        continue
                    seen.add(k)
                    uniq.append(k)
                return uniq

            def is_relevant_news_item(title: str, content: str, alias_terms: list) -> bool:
                text = re.sub(r"\s+", " ", f"{title or ''} {content or ''}").lower()
                if not text or not alias_terms:
                    return True
                # 至少命中一个公司实体词或股票码，降低跨公司噪声
                return any(term in text for term in alias_terms)

            if needs_api:
                yield f'data: {json.dumps({"type": "status", "message": "📡 Fetching live multi-source data (Market, News, Reports)..."})}\n\n'
                search_queries = build_news_queries(request.message, stock_code if has_stock else None)
                news_terms = build_news_terms(request.message, stock_code if has_stock else None)
                
                # 使用 asyncio.gather 并发执行 IO 密集型操作
                async def get_stock():
                    return await asyncio.to_thread(MarketDataService.get_stock_data, stock_code) if has_stock else {}
                
                async def get_kline():
                    return await asyncio.to_thread(MarketDataService.get_kline_options, stock_code) if has_stock else None
                
                async def get_live_news():
                    try:
                        items = await asyncio.to_thread(
                            LiveNewsService.fetch,
                            search_queries,
                            8,
                            news_terms,
                            stock_code if has_stock else None,
                        )
                        if items:
                            return items

                        # 一级查询为空时，使用股票代码做轻量兜底，降低“实时新闻=0”的概率
                        if has_stock:
                            fallback_queries = [stock_code, stock_code.split(".")[0]]
                            code_prefix = stock_code.split(".")[0]
                            if code_prefix == "9988":
                                fallback_queries.extend(["Alibaba 9988.HK", "BABA Alibaba"])
                            fallback_terms = list(news_terms)
                            fallback_terms.extend(fallback_queries)
                            return await asyncio.to_thread(
                                LiveNewsService.fetch,
                                fallback_queries,
                                6,
                                fallback_terms,
                                stock_code,
                            )
                        return []
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

                alias_terms = build_company_alias_terms(stock_code if has_stock else None, request.message)
                live_news_items = [
                    x for x in live_news_items
                    if is_relevant_news_item(x.get("title", ""), x.get("content", ""), alias_terms)
                ]
                if len(live_news_items) > 6:
                    live_news_items = live_news_items[:6]
                
                live_news_text = format_live_news(live_news_items)
                
                if query_embedding:
                    news_list = await asyncio.to_thread(NewsService.search_similar_news, db, query_embedding, stock_code if has_stock else None, 2)
                else:
                    news_list = await asyncio.to_thread(NewsService.get_news_by_stock, db, stock_code, 2) if has_stock else []

                news_list = [
                    n for n in news_list
                    if is_relevant_news_item(getattr(n, "title", ""), getattr(n, "content", ""), alias_terms)
                ]

                source_entries = build_source_entries(live_news_items, news_list)
                source_evidence_text = build_source_evidence(source_entries)

                yield f'data: {json.dumps({"type": "status", "message": f"📰 Live news: {len(live_news_items)} | Cached docs: {len(news_list)}"})}\n\n'
                    
                db_news_text = format_news(news_list)
                news_text = f"[Live Real-time News]\n{live_news_text if live_news_text else 'No recent live news'}\n[Recent Historical News Match]\n{db_news_text}"
                
            else:
                stock_data = {}
                chart_options_str = None
                news_text = ""
            
            yield f'data: {json.dumps({"type": "status", "message": "🧠 AI is reasoning..."})}\n\n'

            # 获取最近几条对话历史组合到上下文
            history_chats = ChatService.get_chat_history(db, limit=3, username=x_username)
            same_lang_history = []
            for c in history_chats:
                if detect_text_language(c.user_message or "") == response_lang:
                    same_lang_history.append(f"User: {c.user_message}\nAI: {c.ai_response}")
            history_text = "\n".join(same_lang_history)

            language_name = "English" if lang_is_en else "Chinese"
            source_tail_heading = "### 🔗 Sources" if lang_is_en else "### 🔗 参考来源"
            source_hint_text = "See references at the end." if lang_is_en else "参考来源见文末。"
            no_news_fallback = "No specific related news found currently." if lang_is_en else "当前未检索到特定相关资讯。"
            general_disclaimer = (
                "*⚠️ Analysis is for reference only, not investment advice.*"
                if lang_is_en
                else "*⚠️ 分析仅供参考，不构成投资建议。*"
            )

            if lang_is_en:
                required_headings = """- `### 🎯 Core Fundamentals`
      - `### 📈 Price Trend & Market Analysis`
      - `### 📰 Recent Key News`
      - `### 💼 Financials & Fundamentals`
      - `### 📌 Summary & Outlook`"""
                news_origin_rule = "Use `[Live News]` for recent items and `[DB Record]` for historical records."
                no_data_reply = "Sorry, the system could not retrieve relevant financial data..."
                deep_disclaimer = "*⚠️ AI deep analysis is for reference only, the market is highly volatile, and this does not constitute substantive investment advice.*"
            else:
                required_headings = """- `### 🎯 核心基础数据`
      - `### 📈 股价趋势与盘面分析`
      - `### 📰 近期关键新闻详述`
      - `### 💼 简短财务与基本面分析`
      - `### 📌 总结与展望`"""
                news_origin_rule = "使用 `[实时新闻]` 标记近期资讯，使用 `[数据库收录]` 标记历史收录资讯。"
                no_data_reply = "抱歉，系统暂时无法检索到该公司的有效金融数据..."
                deep_disclaimer = "*⚠️ AI深度分析仅供综合参考，市场具有高波动性，本分析不构成任何实质性投资建议。*"
            
            # 构建Prompt
            if has_stock:
                if stock_data and stock_data.get('trend'):
                    trend_info = f"\n- **10-Day K-Line Trend**: {stock_data.get('trend')}"
                else:
                    trend_info = ""
                price_info = f"- **Current Price**: {stock_data.get('price', 'Unknown')} USD\n- **Today Change**: {stock_data.get('change', 'Unknown')}%\n- **Volume**: {stock_data.get('volume', 'Unknown')}{trend_info}" if stock_data else "Currently unable to get latest market data for this stock."

                prompt = f"""You are a professional AI stock analyst. Generate an in-depth analytical response directly without any formal greetings, filler introductions or self-introductions.

### Chat History Context
(Note: Use this history for context only. DO NOT copy any old formatting or sections like "核心观点摘要" from the history. You MUST strictly use the NEW headings defined below.)
{history_text if history_text else "No chat history"}

**User Message**: {request.message}

### Current Market Data ({stock_code})
{price_info}

### Recent Core News
{news_text if news_text else 'No latest related news'}

### Structured Source Notes
{source_evidence_text}

**Answering Principles**:
1. **Strict Fact Anchoring**: If NO information about the requested company exists, you MUST reply exactly: "{no_data_reply}"
2. **Use EXACT markdown headings below** (DO NOT add extra `##` text, just use H3 `###`):
        {required_headings}
3. **Deep News & Time Differentiation (crucial)**: In the **Recent Key News** section, strictly summarize the provided news articles with rich details. **Crucial Rule 1**: Each bullet MUST explicitly start with an origin label. {news_origin_rule} **Crucial Rule 2**: You MUST explicitly state the exact date of the news. **Crucial Rule 3**: NEVER write empty descriptions like "the article discusses the performance". You MUST extract the actual facts, core events, numbers, or direct conclusions from the text.
4. **Data Isolation (Crucial)**: In the **Core Fundamentals** section, provide exactly ONE bulleted list stating the Current Price, Today's Change, and Volume. DO NOT do any analysis in this section.
5. **Deep Trend Analysis**: In the **Price Trend & Market Analysis** section, YOU MUST EXPLICITLY MENTION AND ANALYZE the provided **10-Day K-Line Trend** data (e.g., list the distinct price points over the last 10 days). DO NOT mention today's volume or change again. Focus entirely on the mathematical momentum (e.g., support/resistance levels inferred from the 10-day history) and the psychology behind the recent volatility.
6. **No Repetition Rule (Crucial)**: DO NOT repeat any of the basic metrics (price, volume, change) outside of the first Core Fundamentals section. Each subsequent section must provide NEW insights without copy-pasting numbers.
7. **Detailed Conclusion**: In the **Summary & Outlook** section, provide a clear, final synthesis of the trend, news, and fundamentals, offering actionable perspectives on the stock's short-term outlook.
8. **Professional Typography & Formatting**: Use emojis seamlessly. Add **bolding** to ALL key dates, source origins, and numbers.
9. **Citation rule**: Every bullet in the news section must map to a specific source tag like `[S1]`, `[S2]`.
10. **No URLs or markdown links in the main body**: Do not include hyperlinks or raw URLs in the main body; only use citation tags. (Links will be appended separately by the system.)
11. **Conciseness & Tone**: Do not use generic filler phrases (e.g., "we need to pay close attention to", "this will help investors make better decisions"). Provide direct, dense, and objective insights.
12. **Language Matching (Hard Constraint)**: You MUST reply in {language_name} only. Ignore other-language cues from chat history, news snippets, and examples.
13. **Disclaimer**: You MUST start a new line at the very end of your response with exactly: {deep_disclaimer}"""

            elif needs_api:
                prompt = f"""You are an intelligent AI assistant. Please answer the following questions in detail using Markdown format.

### Chat History Context
(Note: Use this history for context only. DO NOT copy its formatting, sections, or layout if it doesn't fit the current question.)
{history_text if history_text else "No chat history"}

**User Message**: {request.message}

### Reference News
{news_text if news_text else 'None'}

**Requirements**:
1. **Identify General vs Specific Domain Questions**: If the user asks general knowledge questions, ignore the financial context and answer accurately as a general-purpose AI.
2. If it is a macro-market or industry question, objectively answer based on provided news and your own knowledge.
3. **No URLs or markdown links in the main body**: Do not include hyperlinks or markdown link syntax in the streamed analysis; just mention "{source_hint_text}". (Links will be appended separately by the system.)
4. **Keep it concise and non-repetitive**: Do not use generic filler phrases (e.g., "we need to pay close attention to", "this will help investors make better decisions"). Provide direct, dense, and objective insights.
5. **Language Matching (Hard Constraint)**: You MUST reply in {language_name} only. Ignore other-language cues from chat history and references.
6. If it is a finance question but no relevant news is found, explicitly state "{no_news_fallback}", then answer based on existing knowledge.
7. **Disclaimer**: You MUST start a new line at the very end of your response with exactly: {general_disclaimer}"""

            else:
                prompt = f"""You are a smart and friendly AI assistant. The user's current question is not related to a specific stock.
Answer casually, comprehensively, and helpfully as a general-purpose LLM.
Do not force connections to stock data or financial jargon.

**Language Matching**: You MUST reply in the exact same language as the **User Message**. If the user asks in English, your ENTIRE response MUST be in English.
**Language Matching (Hard Constraint)**: You MUST reply in {language_name} only.

**User Message**: {request.message}"""
            
            # 流式生成回到
            markdown_link_pattern = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)")
            url_pattern = re.compile(r"https?://\S+")
            ai_response = ""
            for chunk in LLMService.generate_stream(prompt):
                # 屏蔽正文中的链接，避免URL逐字流式输出造成观感差
                safe_chunk = markdown_link_pattern.sub(r"[\1]", chunk)
                safe_chunk = url_pattern.sub("", safe_chunk)
                ai_response += safe_chunk
                yield f'data: {json.dumps({"type": "chunk", "content": safe_chunk})}\n\n'
                await asyncio.sleep(0)

            # 自动追加参考资料，防止LLM流式输出时产生卡顿
            if has_stock and source_entries:
                source_lines = []
                for idx, entry in enumerate(source_entries, 1):
                    source_lines.append(f"- [S{idx}] [{entry['title']}]({entry['url']}) ({entry['date']})")
                if source_lines:
                    sources_md = f"\n\n{source_tail_heading}\n"
                    sources_md += "\n".join(source_lines) + "\n"
                    ai_response += sources_md
                    yield f'data: {json.dumps({"type": "chunk", "content": sources_md})}\n\n' 
            
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
        stock_code = MarketDataService.extract_stock_code(q)
        terms = [q]
        if stock_code:
            terms.extend([stock_code, stock_code.split(".")[0]])
        items = LiveNewsService.fetch(q, limit=limit, terms=terms, stock_code=stock_code)
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
        content_part = getattr(news, 'content', getattr(news, 'summary', ''))   
        content_clean = re.sub(r"https?://\S+", "", content_part or "").strip()
        details = f"\n  > Details: {content_clean[:800]}..." if content_clean else ""
        news_text += f"{i}. **{news.title}** ({news.publish_date}){details}\n\n"

    return news_text

def format_live_news(items: list) -> str:
    """格式化实时抓取的news字典列表"""
    if not items:
        return ""

    text = ""
    for i, item in enumerate(items, 1):
        title = item.get("title", "No Title")
        pub_date = item.get("date", "Just now")
        desc_raw = item.get("content", "")
        desc_clean = re.sub(r'<[^>]+>', '', desc_raw).replace('&nbsp;', ' ').strip()
        desc_clean = re.sub(r"https?://\S+", "", desc_clean).strip()
        details = f"\n  > Details: {desc_clean[:800]}..." if desc_clean else "" 
        text += f"{i}. (Breaking Today) **{title}** ({pub_date}){details}\n\n"
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
