"""
RAG数据提前处理脚本 (Offline Ingestion)
运行此脚本会将 data/raw_docs/ 下的文本文件向量化存入SQLite
"""

import os
import sys
import json
from datetime import datetime
import pypdf

# 注入路径以便可以导入backend模块
sys.path.append(os.path.dirname(__file__))

from database import SessionLocal, init_db
from models import NewsCache
from services.llm_service import LLMService

# 确保存放原始文档的目录存在
DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw_docs')
os.makedirs(DOCS_DIR, exist_ok=True)

def process_documents():
    db = SessionLocal()
    
    files = [f for f in os.listdir(DOCS_DIR) if f.endswith('.txt') or f.endswith('.pdf')]
    if not files:
        print(f"⚠️ 在 {DOCS_DIR} 没有找到 .txt 或 .pdf 文件。")
        print("请在该目录放入命名格式为 '股票代码_标题.txt' 或 '.pdf' 的文件 (例如 '9988.HK_阿里巴巴公司介绍.pdf')")
    
    for filename in files:
        # 解析文件名提取股票代码和标题
        # 假设格式：9988.HK_阿里巴巴2023财报摘要.pdf
        parts = filename.replace('.txt', '').replace('.pdf', '').split('_', 1)
        stock_code = parts[0] if len(parts) > 1 else 'UNKNOWN'
        title = parts[1] if len(parts) > 1 else filename

        filepath = os.path.join(DOCS_DIR, filename)
        
        content = ""
        if filename.endswith('.txt'):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
        elif filename.endswith('.pdf'):
            try:
                reader = pypdf.PdfReader(filepath)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        content += text + "\n"
                content = content.strip()
            except Exception as e:
                print(f"❌ 读取 PDF {filename} 失败: {e}")
                continue
            continue
            
        print(f"⏳ 正在为 [{stock_code}] {title} 生成向量 (可能需要几秒)...")
        
        # 为了不超长Token，简单切块(Chunking)，按500字一个Chunk切分
        chunk_size = 500
        chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]
        
        for idx, chunk in enumerate(chunks):
            if len(chunk) < 10: continue # 太短忽略
            
            # 调用Ollama生成向量
            embedding_vector = LLMService.generate_embedding(chunk)
            
            if embedding_vector:
                # 存入SQLite数据库
                news_item = NewsCache(
                    stock_code=stock_code,
                    title=f"{title} (Part {idx+1})",
                    content=chunk,
                    embedding=json.dumps(embedding_vector),  # 核心：转为JSON字符串存入DB
                    source="Local RAG Docs",
                    publish_date=datetime.now().strftime("%Y-%m-%d"),
                    created_at=datetime.now(),
                    updated_at=datetime.now()
                )
                db.add(news_item)
            else:
                print(f"❌ '{title}' 第 {idx+1} 块生成向量失败。")
        
        db.commit()
        print(f"✅ 文档 '{filename}' 处理完成并存入数据库！")
        
    db.close()
    print("🎉 所有文档处理完毕！现在AI已经拥有了这些向量记忆！")

if __name__ == "__main__":
    init_db()
    process_documents()