# Project Proposal: Intelligent Stock AI Assistant

## 1. Project Idea
This project proposes an "Intelligent Stock AI Assistant," a web-based conversational AI agent powered by Large Language Models (LLMs) and Retrieval-Augmented Generation (RAG). The assistant acts as a personalized financial analyst, providing users with synthesized, natural-language insights by seamlessly combining real-time stock market data, breaking financial news, and deep historical research reports.

## 2. Problem Statement
Retail investors face severe "information overload" in today's fast-paced financial markets. Traditional search engines and stock screeners provide fragmented raw data, requiring significant time and financial expertise to interpret. Meanwhile, raw AI models face "hallucinations" and a lack of real-time market awareness, often providing outdated or incorrect stock prices and ignoring recent corporate events, which can lead to disastrous investment decisions.

## 3. Proposed AI Solution
We propose a robust, multi-pipeline RAG application built on FastAPI. When a user asks a stock-related question, the system employs an intent-recognition engine to extract the financial entity. It then launches concurrent asynchronous data retrievals: fetching live market quotes, crawling real-time web news, and executing a cosine-similarity search against a local vector database of pre-ingested corporate reports. Finally, these multifaceted data streams are assembled into a highly context-aware system prompt, forcing the LLM to generate precise, grounded, and up-to-the-minute financial analysis securely without hallucinating.

## 4. Required Data
*   **Real-time Market Data:** Live pricing, opening/closing rates, and K-line chart configurations fetched via the **Yahoo Finance (YFinance) API**.
*   **Live Event News:** Up-to-the-minute global financial headlines crawled from **Google News RSS** feeds.
*   **Deep Institutional Knowledge:** Historical corporate summaries and in-depth financial reports (e.g., "Alibaba 2024 Summary") locally ingested and vectorized via **FastEmbed** into a SQLite database.

## 5. Main Challenges
*   **Data Latency vs. User Experience:** Fetching real-time quotes, crawling news, and calculating vector similarities sequentially can cause severe delays. This will be mitigated by implementing an aggressive `asyncio.gather` concurrent pipeline.
*   **Vector Search Efficiency:** Implementing a local, lightweight vector search without relying on heavy enterprise databases (like Milvus/Chroma). We will overcome this by designing custom in-memory cosine similarity algorithms operating over JSON-serialized embeddings in SQLite.
*   **Dynamic Intent Routing:** Accurately preventing the AI from launching expensive data-fetching pipelines during basic "chit-chat" conversations.

## 6. Work Allocation (4 Team Members)
*   **Member A (Backend Architecture & AI Core):** Leads the FastAPI framework design. Responsible for the LLM pipeline integration, asynchronous data orchestration (`asyncio.gather`), and system prompt engineering.
*   **Member B (Data Engineering & Vector DB):** Develops the RAG pipeline. Responsible for offline data ingestion scripting (`ingest_data.py`), FastEmbed vectorization, and the SQLite cosine-similarity search algorithms.
*   **Member C (External APIs & Integrations):** Handles all external data sourcing. Responsible for integrating the YFinance API for market data and writing the Google News RSS scraping modules (`live_news_service.py`).
*   **Member D (Frontend Dev & Data Visualization):** Constructs the Vanilla JS/HTML frontend. Responsible for handling SSE (Server-Sent Events) streaming responses and rendering interactive K-line stock charts on the UI.