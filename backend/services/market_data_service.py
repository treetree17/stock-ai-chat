"""
行情服务（无 Tushare 依赖）
- 优先使用 yfinance 获取最新价/涨跌幅/成交量
- 失败则提供本地兜底示例数据
"""

import re
from datetime import datetime, timedelta

import requests

try:
    import yfinance as yf
except Exception:
    yf = None


class MarketDataService:
    """行情服务（yfinance + 本地兜底）"""

    _alias_map = {
        # Hong Kong
        "s&p 500": "^GSPC",
        "sp500": "^GSPC",
        "s&p": "^GSPC",
        "dow jones": "^DJI",
        "nasdaq": "^IXIC",
        "阿里": "9988.HK",
        "阿里巴巴": "9988.HK",
        "baba": "9988.HK",
        "腾讯": "0700.HK",
        "騰訊": "0700.HK",
        "tencent": "0700.HK",
        "美团": "3690.HK",
        "美團": "3690.HK",
        "meituan": "3690.HK",
        "网易": "9999.HK",
        "網易": "9999.HK",
        "netease": "9999.HK",
        "京东": "9618.HK",
        "京東": "9618.HK",
        "jd.com": "9618.HK",

        # US tech
        "苹果": "AAPL",
        "apple": "AAPL",
        "aapl": "AAPL",
        "微软": "MSFT",
        "微軟": "MSFT",
        "microsoft": "MSFT",
        "msft": "MSFT",
        "谷歌": "GOOGL",
        "谷歌a": "GOOGL",
        "google": "GOOGL",
        "alphabet": "GOOGL",
        "亚马逊": "AMZN",
        "亞馬遜": "AMZN",
        "amazon": "AMZN",
        "amzn": "AMZN",
        "特斯拉": "TSLA",
        "tesla": "TSLA",
        "tsla": "TSLA",
        "英伟达": "NVDA",
        "英偉達": "NVDA",
        "nvidia": "NVDA",
        "nvda": "NVDA",
        "脸书": "META",
        "臉書": "META",
        "meta": "META",
        "facebook": "META",
        "奈飞": "NFLX",
        "奈飛": "NFLX",
        "netflix": "NFLX",
        "amd": "AMD",
        "超微": "AMD",
        "英特尔": "INTC",
        "英特爾": "INTC",
        "intel": "INTC",
        
        # 中概股补充
        "拼多多": "PDD",
        "pdd": "PDD",
        "百度": "BIDU",
        "baidu": "BIDU",
        "理想": "LI",
        "理想汽车": "LI",
        "蔚来": "NIO",
        "小鹏": "XPEV",
        "小鹏汽车": "XPEV",
        "b站": "BILI",
        "哔哩哔哩": "BILI",

        # US consumer/industrial
        "波音": "BA",
        "boeing": "BA",
        "可口可乐": "KO",
        "可口可樂": "KO",
        "coca cola": "KO",
        "星巴克": "SBUX",
        "starbucks": "SBUX",
        "costco": "COST",

        # China A-share (add exchange suffix for yfinance)
        "茅台": "600519.SS",
        "貴州茅台": "600519.SS",
        "贵州茅台": "600519.SS",
        "招商银行": "600036.SS",
        "招商銀行": "600036.SS",
        "平安": "601318.SS",
        "中国平安": "601318.SS",
        "中國平安": "601318.SS",
        "宁德时代": "300750.SZ",
        "寧德時代": "300750.SZ",
        "中免": "601888.SS",
        "中国中免": "601888.SS",
        "中國中免": "601888.SS",
        "美的": "000333.SZ",
        "美的集团": "000333.SZ",
        "美的集團": "000333.SZ",
        "格力": "000651.SZ",
        "格力电器": "000651.SZ",
        "格力電器": "000651.SZ",
        "比亚迪": "002594.SZ",
        "比亞迪": "002594.SZ",
    }

    _cache = {}
    _cache_time = {}
    _search_cache = {}
    _search_cache_time = {}

    @staticmethod
    def extract_stock_code(message: str) -> str:
        """从消息中提取股票代码"""
        if not message:
            return None

        lowered = message.lower()
        patterns = [
            r"([0-9]{1,5}\.(?:SZ|SH|HK))",
            r"([A-Z]{1,5})",
        ]

        for key, value in MarketDataService._alias_map.items():
            if key in lowered:
                return value

        for pattern in patterns:
            match = re.search(pattern, message, flags=re.IGNORECASE)
            if match:
                return match.group(1).upper()

        query = MarketDataService._guess_search_query(message)
        if query:
            symbol = MarketDataService._search_symbol(query)
            if symbol:
                return symbol

        return None

    @staticmethod
    def _guess_search_query(message: str) -> str:
        """从消息中粗略提取公司名供搜索，避免整句噪音。"""
        phrases = re.findall(r"[A-Za-z][A-Za-z\s\.\-&]{1,40}", message)
        if not phrases:
            return None
        candidate = max(phrases, key=len).strip()
        return candidate if len(candidate) >= 2 else None

    @staticmethod
    def _search_symbol(query: str) -> str:
        """调用 Yahoo Finance 搜索接口根据公司名反查代码，结果缓存6小时。"""
        cache_key = query.lower()
        cache_hit = MarketDataService._search_cache.get(cache_key)
        cache_time = MarketDataService._search_cache_time.get(cache_key)
        if cache_hit and cache_time and datetime.now() - cache_time < timedelta(hours=6):
            return cache_hit

        if not yf:
            return None

        try:
            resp = requests.get(
                "https://query2.finance.yahoo.com/v1/finance/search",
                params={"q": query, "lang": "en-US", "region": "US"},
                timeout=5,
            )
            resp.raise_for_status()
            quotes = resp.json().get("quotes") or []
            for quote in quotes:
                symbol = quote.get("symbol")
                if not symbol:
                    continue
                symbol = symbol.upper()
                MarketDataService._search_cache[cache_key] = symbol
                MarketDataService._search_cache_time[cache_key] = datetime.now()
                return symbol
        except Exception as exc:
            print(f"⚠️ Failed to search stock code: {exc}")

        return None

    @staticmethod
    def _fetch_tencent_finance(stock_code: str) -> dict:
        """使用腾讯财经API获取最新行情作为兜底"""
        try:
            code = stock_code.upper()
            if code.endswith('.HK'):
                num = code.split('.')[0]
                tc_code = f"hk{num.zfill(5)}"
            elif code.endswith('.SS') or code.endswith('.SH'):
                num = code.split('.')[0]
                tc_code = f"sh{num}"
            elif code.endswith('.SZ'):
                num = code.split('.')[0]
                tc_code = f"sz{num}"
            else:
                tc_code = f"us{code}"
                
            resp = requests.get(f"https://qt.gtimg.cn/q={tc_code}", timeout=5)
            text = resp.text
            if "v_" in text and "~" in text:
                parts = text.split('~')
                if len(parts) > 32:
                    price = round(float(parts[3]), 2)
                    change_pct = round(float(parts[32]), 2)
                    vol_raw = float(parts[6])
                    # A股成交量单位通常为手(100股)
                    if tc_code.startswith('sh') or tc_code.startswith('sz'):
                        vol_raw *= 100
                        
                    return {
                        "price": price,
                        "change": change_pct,
                        "volume": f"{vol_raw / 1e6:.1f}M",
                        "pe": "N/A"
                    }
        except Exception as e:
            print(f"⚠️ Tencent Finance API error: {e}")
        return {}

    @staticmethod
    def get_stock_data(stock_code: str) -> dict:
        """获取股票数据（带缓存，优先 yfinance，备用腾讯财经）"""

        if stock_code in MarketDataService._cache:
            cache_time = MarketDataService._cache_time.get(stock_code)
            if cache_time and datetime.now() - cache_time < timedelta(minutes=30):
                return MarketDataService._cache[stock_code]

        data = {}
        try:
            # 1. 尝试使用 yfinance (使用 5d 获取最近一天防止周末为空)
            if yf:
                ticker = yf.Ticker(stock_code)
                df = ticker.history(period="5d")
                
                if not df.empty:
                    last = df.iloc[-1]
                    price = round(float(last.get("Close", last.get("close", 0))), 2)
                    open_price = float(last.get("Open", last.get("open", price))) or price
                    change_pct = ((price - open_price) / open_price * 100) if open_price else 0.0
                    volume_raw = float(last.get("Volume", last.get("volume", 0)))
                    data = {
                        "price": price,
                        "change": round(change_pct, 2),
                        "volume": f"{volume_raw / 1e6:.1f}M",
                        "pe": "N/A",
                    }
        except Exception as e:
            print(f"⚠️ yfinance fetch failed, trying fallback API (Error: {e})")
            
        # 2. 如果 yfinance 没取到数据或失败，使用腾讯财经作为兜底
        if not data:
            data = MarketDataService._fetch_tencent_finance(stock_code)

        if data:
            MarketDataService._cache[stock_code] = data
            MarketDataService._cache_time[stock_code] = datetime.now()
            
        return data

    @staticmethod
    def get_kline_options(stock_code: str) -> str:
        """获取近期K线图的ECharts Options JSON，返回最近1或2个月K线"""
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{stock_code}?range=2mo&interval=1d"
            headers = {"User-Agent": "Mozilla/5.0"}
            resp = requests.get(url, headers=headers, timeout=5)
            data = resp.json()
            
            result = data.get("chart", {}).get("result", [])
            if not result:
                return None
                
            indicators = result[0].get("indicators", {}).get("quote", [{}])[0]
            timestamps = result[0].get("timestamp", [])
            
            if not indicators or not timestamps:
                return None
                
            opens = indicators.get("open", [])
            closes = indicators.get("close", [])
            lows = indicators.get("low", [])
            highs = indicators.get("high", [])
            
            # 组装数据 (时间, [开, 收, 低, 高])
            x_data = []
            y_data = []
            
            for i, ts in enumerate(timestamps):
                if opens[i] is None or closes[i] is None:
                    continue
                dt_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
                x_data.append(dt_str)
                # Pyecharts K线数据格式：[open, close, lowest, highest]
                y_data.append([
                    round(opens[i], 2), 
                    round(closes[i], 2), 
                    round(lows[i], 2), 
                    round(highs[i], 2)
                ])
                
            if not x_data:
                return None
                
            from pyecharts.charts import Kline
            from pyecharts import options as opts
            
            kline = Kline()
            kline.add_xaxis(x_data)
            kline.add_yaxis(
                series_name=stock_code,
                y_axis=y_data,
                itemstyle_opts=opts.ItemStyleOpts(
                    color="#ef232a",
                    color0="#14b143",
                    border_color="#ef232a",
                    border_color0="#14b143",
                )
            )
            kline.set_global_opts(
                title_opts=opts.TitleOpts(title=f"{stock_code} - Recent K-line Trend"),
                xaxis_opts=opts.AxisOpts(is_scale=True),
                yaxis_opts=opts.AxisOpts(
                    is_scale=True,
                    splitarea_opts=opts.SplitAreaOpts(
                        is_show=True, areastyle_opts=opts.AreaStyleOpts(opacity=1)
                    ),
                ),
                datazoom_opts=[opts.DataZoomOpts(type_="inside")],
            )
            return kline.dump_options()
            
        except Exception as e:
            print(f"⚠️ Failed to generate K-line chart: {e}")
            return None

