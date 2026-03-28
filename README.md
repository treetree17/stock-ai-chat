# 📈 股票投资AI助手

基于LLM的智能股票分析助手，使用FastAPI + SQLite + YFinance打造的MVP版本。

## ✨ 特性

- 🤖 **AI驱动**：使用LLM模型回答股票问题
- 📊 **实时数据**：集成YFinance获取最新股票行情数据
- 💾 **数据持久化**：SQLite本地存储对话历史
- ⚡ **快速响应**：4-6秒内返回分析结果
- 🎨 **简洁UI**：原生HTML/CSS/JavaScript无框架依赖
- 📈 **成本追踪**：记录API调用成本

## 🚀 快速开始

### 前置条件
- Python 3.9+
- LLM API Key (如果是本地模型则无需)

### 安装步骤

1. **克隆仓库**
```bash
git clone https://github.com/treetree17/stock-ai-chat.git
cd stock-ai-chat
```

2. **创建虚拟环境**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

3. **安装依赖**
```bash
pip install -r backend/requirements.txt
```

4. **配置环境变量**
```bash
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入你的API KEY
```

5. **启动后端**（自动初始化数据库）
```bash
cd backend
uvicorn main:app --reload --port 8000
```

6. **启动前端**（新终端）
```bash
cd frontend
python -m http.server 8080
```

7. **访问应用**
打开浏览器访问 `http://localhost:8080`

## 📖 使用示例

```
用户：最近阿里巴巴怎么样？
AI：阿里巴巴近期表现强势，上周上涨2.3%。
   利好因素：
   1. 云计算业务增速加快
   2. AI投资初见成效
   建议关注下周的财报发布。
```

## 🏗️ 项目结构

```
stock-ai-chat/
├── backend/
│   ├── main.py                 # FastAPI主程序
│   ├── database.py             # 数据库配置
│   ├── models.py               # SQLAlchemy模型
│   ├── config.py               # 配置管理
│   ├── services/               # 业务逻辑
│   │   ├── chat_service.py
│   │   ├── tushare_service.py
│   │   ├── market_data_service.py
│   │   ├── llm_service.py
│   │   ├── news_service.py
│   │   ├── live_cache.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── style.css
│   └── app.js
├── data/
│   └── app.db                  # SQLite数据库（自动生成）
└── README.md
```

## 🔌 API接口

| 端点 | 方法 | 说明 |
|------|------|------|
| /api/chat | POST | 发送消息，获取AI回答 |
| /api/history | GET | 获取对话历史 |
| /api/stats | GET | 获取成本统计 |
| /api/history | DELETE | 清空对话历史 |
| /health | GET | 健康检查 |

## 📊 性能指标

| 指标 | 值 |
|------|-----|
| 启动时间 | <3秒 |
| 响应时间 | 4-6秒 |
| 内存占用 | <100MB |
| 首页加载 | <0.5秒 |

## 💡 技术栈

- **后端**：FYahoo Finance, LLM Uvicorn
- **数据源**：Tushare API, OpenAI API
- **数据库**：SQLite3
- **前端**：HTML5, CSS3, Vanilla JavaScript

## 🔮 后续规划

- [ ] 用户账户系统
- [ ] 更复杂的RAG向量检索
- [ ] Telegram Bot集成
- [ ] 升级到PostgreSQL
- [ ] 云端部署（AWS/Heroku）

## ⚠️ 免责声明

本项目仅供学习和演示使用，生成的投资建议**不构成投资指导**，请独立判断并承担相应风险。

## 📝 许可证

MIT License

## 👨‍💻 联系方式

如有问题或建议，欢迎提Issue或PR！

---

**Made with ❤️ by treetree17**