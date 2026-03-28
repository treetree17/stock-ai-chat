"""
配置管理
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# API配置
LLM_API_KEY = os.getenv('LLM_API_KEY', 'kOViQoVw')
LLM_HOST = os.getenv('LLM_HOST', 'http://144.214.54.47')  # 远端推理服务

# Embedding 配置：本地 fastembed（无服务依赖），如需改回 Ollama 可自行切换
FASTEMBED_MODEL = os.getenv('FASTEMBED_MODEL', 'BAAI/bge-small-zh-v1.5')
LLM_EMBED_HOST = os.getenv('LLM_EMBED_HOST', 'http://127.0.0.1:11434')
LLM_EMBED_MODEL = os.getenv('LLM_EMBED_MODEL', 'nomic-embed-text')

# 数据库配置（默认指向项目根目录下 data/app.db）
DEFAULT_DB_PATH = BASE_DIR / "data" / "app.db"
DATABASE_URL = f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"

# 日志配置
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# 应用配置
APP_NAME = "股票AI助手"
APP_VERSION = "1.0.0"

# 验证必要的配置
if not LLM_API_KEY:
    print("⚠️ 警告：未找到LLM_API_KEY，请在.env中配置")
