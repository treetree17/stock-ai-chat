"""
行情服务（无 Tushare 依赖）
- 优先使用 yfinance 获取最新价/涨跌幅/成交量
- 失败则提供本地兜底示例数据
"""

import re
from datetime import datetime, timedelta

import requests

try:
    from alias_config import MARKET_ALIAS_MAP, load_extended_alias_map
except Exception:
    from backend.alias_config import MARKET_ALIAS_MAP, load_extended_alias_map

try:
    import yfinance as yf
except Exception:
    yf = None

_extended_alias_map = load_extended_alias_map()

class MarketDataService:
    """行情服务（yfinance + 本地兜底）"""

    _alias_map = MARKET_ALIAS_MAP

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

        for key, value in _extended_alias_map.items():
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
        """从消息中粗略提取公司/股票名称供搜索"""
        clean_msg = message
        
        # 1. 英文停用词（使用词边界正则，忽略大小写，防止误伤公司名中的字母组合）
        en_stopwords = [
            r"give", r"me", r"show", r"tell", r"what", r"is", r"the", r"stock", r"price", 
            r"data", r"of", r"for", r"company", r"information", r"trend", r"analysis", 
            r"quote", r"chart", r"about", r"check", r"share", r"market", r"please", 
            r"can", r"you", r"get", r"analyze"
        ]
        pattern = re.compile(r'\b(' + '|'.join(en_stopwords) + r')\b', re.IGNORECASE)
        clean_msg = pattern.sub(" ", clean_msg)

        # 2. 中文常见停用词（直接字符串替换）
        cn_stopwords = ["给我", "请", "帮我", "查一下", "查询", "的", "股票", "数据", "行情", "走势", "分析", "一下", "公司", "股价", "信息", "展示", "看看", "多少"]
        for word in cn_stopwords:
            clean_msg = clean_msg.replace(word, " ")
        
        # 首先尝试英文名称匹配
        phrases = re.findall(r"[A-Za-z][A-Za-z\s\.\-&]{1,40}", clean_msg)

        # 补充：尝试提取连续的中文名称
        cn_phrases = re.findall(r"[\u4e00-\u9fa5]{2,10}", clean_msg)
        phrases.extend(cn_phrases)

        if not phrases:
            return None

        # 选出最长的词作为搜索词
    @staticmethod
    def _search_symbol(query: str) -> str:
        """调用 Yahoo Finance 和 Tencent Smartbox 根据公司名反查代码"""
        cache_key = query.lower()
        cache_hit = MarketDataService._search_cache.get(cache_key)
        cache_time = MarketDataService._search_cache_time.get(cache_key)
        if cache_hit and cache_time and datetime.now() - cache_time < timedelta(hours=6):
            return cache_hit

        # 优先尝试腾讯财经智能搜索(支持拼音和中文名称)
        try:
            resp = requests.get(f"https://smartbox.gtimg.cn/s3/?v=2&q={query}&t=all", timeout=2)
            text = resp.text
            if "v_hint=" in text:
                hints_str = text.split('="')[1].strip('"\n; ')
                hints = hints_str.split('^')
                for hint in hints:
                    parts = hint.split('~')
                    if len(parts) >= 2:
                        market = parts[0]
                        code = parts[1]
                        ret = None
                        if market == "hk": ret = f"{code}.HK"
                        elif market == "us": ret = code.split('.')[0].upper()
                        elif market == "sh": ret = f"{code}.SS"
                        elif market == "sz": ret = f"{code}.SZ"
                        
                        if ret:
                            MarketDataService._search_cache[cache_key] = ret
                            MarketDataService._search_cache_time[cache_key] = datetime.now()
                            return ret
        except Exception as e:
            print(f"⚠️ Tencent Smartbox failed: {e}")

        # 如果没有yfinance，或者腾讯搜不到，用原来的 Yahoo Finance
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
            # 1. 尝试使用 yfinance (对HK股票进行代码处理，如 00288.HK -> 0288.HK)
            if yf:
                yf_stock_code = stock_code
                if yf_stock_code.endswith('.HK'):
                    parts = yf_stock_code.split('.')
                    # HK 股票在 Yahoo Finance 一般最高保留 4 位数字
                    if len(parts[0]) == 5 and parts[0].startswith('0'):
                        yf_stock_code = parts[0][1:] + '.HK'

                ticker = yf.Ticker(yf_stock_code)
                df = ticker.history(period="10d")
                if not df.empty:
                    last = df.iloc[-1]
                    price = round(float(last.get("Close", last.get("close", 0))), 2)
                    open_price = float(last.get("Open", last.get("open", price))) or price
                    change_pct = ((price - open_price) / open_price * 100) if open_price else 0.0
                    volume_raw = float(last.get("Volume", last.get("volume", 0)))
                    
                    # 提取最近10个交易日的收盘价趋势，供LLM分析
                    try:
                        history_prices = []
                        for idx, row in df.iterrows():
                            date_str = idx.strftime('%m-%d')
                            close_p = round(float(row.get("Close", row.get("close", 0))), 2)
                            history_prices.append(f"{date_str}: {close_p}")
                        trend_str = " -> ".join(history_prices)
                    except:
                        trend_str = "N/A"
                    
                    data = {
                        "price": price,
                        "change": round(change_pct, 2),
                        "volume": f"{volume_raw / 1e6:.1f}M",
                        "pe": "N/A",
                        "trend": trend_str
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
            yf_stock_code = stock_code
            if yf_stock_code.endswith('.HK'):
                parts = yf_stock_code.split('.')
                if len(parts[0]) == 5 and parts[0].startswith('0'):
                    yf_stock_code = parts[0][1:] + '.HK'
                    
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_stock_code}?range=2mo&interval=1d"
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

