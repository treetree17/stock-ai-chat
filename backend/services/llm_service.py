"""
LLM服务 - Ollama API调用 (Llama3.3 70B)
"""

import os
from ollama import Client
from config import LLM_API_KEY, LLM_HOST, LLM_EMBED_HOST, LLM_EMBED_MODEL, FASTEMBED_MODEL
from sentence_transformers import SentenceTransformer

# 推理客户端（远端 70B）
client = Client(
    host=LLM_HOST,
    headers={'Authorization': f'Bearer {LLM_API_KEY}'}
)

# 本地无服务嵌入器（延迟加载，避免阻塞系统启动）
_local_embedder = None
# 备用：Ollama 嵌入客户端（可选）
embed_client = Client(host=LLM_EMBED_HOST)

class LLMService:
    """LLM API调用服务"""
    
    @staticmethod
    def generate_response(prompt: str) -> str:
        """调用LLM生成回答"""
        try:
            # 组合System Prompt和User Prompt
            full_prompt = f"你是一套严肃、专业的金融AI分析系统。请直接给出分析结果，不要包含任何自我介绍、寒暄或冗余的开场白（例如不要说“作为一名资深分析师”或“我很乐意为您提供”）。直接进入正题。\n\n{prompt}"
            
            response_stream = client.generate(
                model='llama3.3:is6620',
                prompt=full_prompt,
                stream=True
            )
            
            # 由于FastAPI当前端点是同步等待所有结果，所以我们收集所有流返回拼接
            full_response = ""
            for chunk in response_stream:
                full_response += chunk['response']
                
            return full_response
        
        except Exception as e:
            print(f"⚠️ LLM API错误: {e}")
            return f"抱歉，我现在无法生成回答。错误：{str(e)}"

    @staticmethod
    def generate_stream(prompt: str):
        """流式调用LLM生成回答"""
        try:
            full_prompt = f"你是一套严肃、专业的金融AI分析系统。请直接给出分析结果，不要包含任何自我介绍、寒暄或冗余的开场白（例如不要说“作为一名资深分析师”或“我很乐意为您提供”）。直接进入正题。\n\n{prompt}"
            
            response_stream = client.generate(
                model='llama3.3:is6620',
                prompt=full_prompt,
                stream=True
            )
            
            for chunk in response_stream:
                yield chunk['response']
        
        except Exception as e:
            print(f"⚠️ LLM API错误: {e}")
            yield f"\n[后台服务错误]: {str(e)}"
    
    @staticmethod
    def generate_embedding(text: str) -> list[float]:
        """调用本地 SentenceTransformer 生成文本向量"""
        global _local_embedder
        try:
            # 优先本地 SentenceTransformer，使用预先下载在本地 models 目录里的模型
            if _local_embedder is None:
                print("⏳ 将从本地 models/ 目录加载 Embedding 模型...")
                model_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models/bge-small-zh-v1.5")
                _local_embedder = SentenceTransformer(model_dir)
            
            emb = _local_embedder.encode(text)
            emb_list = [float(x) for x in emb] if emb is not None else []
            if emb_list:
                return emb_list

            # 备用：Ollama 嵌入
            response = embed_client.embeddings(
                model=LLM_EMBED_MODEL,
                prompt=text
            )
            return response.get('embedding', [])
        except Exception as e:
            print(f"⚠️ Embedding API错误: {e}")
            return []
