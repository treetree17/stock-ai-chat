"""
集中管理股票别名映射。

- COMPANY_ALIASES: 代码 -> 常见别名列表（用于新闻相关词扩展）
- MARKET_ALIAS_MAP: 别名 -> 标准股票代码（用于消息中提取代码）
"""

from pathlib import Path
import json


COMPANY_ALIASES = {
    "9988": ["阿里", "阿里巴巴", "alibaba", "baba", "taobao", "天猫", "淘宝", "alicloud", "菜鸟"],
    "0700": ["腾讯", "tencent", "wechat", "微信"],
    "3690": ["美团", "meituan"],
    "01810": ["小米", "xiaomi", "miui", "雷军"],
    "9618": ["京东", "jd", "jingdong"],
    "9999": ["网易", "netease"],
    "BIDU": ["百度", "baidu"],
    "PDD": ["拼多多", "pinduoduo", "pdd"],
    "BILI": ["b站", "bilibili", "哔哩哔哩"],
    "XPEV": ["小鹏", "xpeng"],
    "NIO": ["蔚来", "nio"],
    "LI": ["理想", "li auto"],
    "AAPL": ["苹果", "apple", "iphone"],
    "MSFT": ["微软", "microsoft", "windows"],
    "GOOGL": ["谷歌", "google", "alphabet"],
    "AMZN": ["亚马逊", "amazon", "aws"],
    "TSLA": ["特斯拉", "tesla", "tsla", "elon musk"],
    "NVDA": ["英伟达", "nvidia", "nvda", "黄仁勋"],
    "META": ["脸书", "meta", "facebook", "zuckerberg"],
}


MARKET_ALIAS_MAP = {
    # 指数
    "s&p 500": "^GSPC",
    "sp500": "^GSPC",
    "s&p": "^GSPC",
    "dow jones": "^DJI",
    "nasdaq": "^IXIC",

    # 港股与中概股常用别名、英文名
    "阿里": "9988.HK",
    "阿里巴巴": "9988.HK",
    "小米": "01810.HK",
    "小米集团": "01810.HK",
    "xiaomi": "01810.HK",
    "baba": "9988.HK",
    "腾讯": "0700.HK",
    "tencent": "0700.HK",
    "meituan": "3690.HK",
    "netease": "9999.HK",
    "jd.com": "9618.HK",
    "拼多多": "PDD",
    "pdd": "PDD",
    "百度": "BIDU",
    "baidu": "BIDU",
    "理想": "LI",
    "理想汽车": "LI",
    "蔚来": "NIO",
    "小鹏": "XPEV",
    "小鹏汽车": "XPEV",
    "xpeng": "XPEV",
    "b站": "BILI",
    "哔哩哔哩": "BILI",
    "bilibili": "BILI",
    "携程": "TCOM",
    "ctrip": "TCOM",
    "trip.com": "TCOM",
    "贝壳": "TCOM",
    "唯品会": "VIPS",
    "vipshop": "VIPS",
    "富途": "FUTU",
    "futu": "FUTU",
    "好未来": "VIPS",
    "腾讯音乐": "TME",
    "爱奇艺": "IQ",
    "iqiyi": "IQ",

    # 中资金融股别名
    "中行": "601988.SS",
    "工行": "601398.SS",
    "建行": "601398.SS",
    "农行": "601288.SS",
    "交行": "601328.SS",
    "邮储银行": "601658.SS",
    "人寿": "601628.SS",
    "太保": "601318.SS",
    "平安银行": "601318.SS",

    # 美股科技与消费
    "苹果": "AAPL",
    "apple": "AAPL",
    "aapl": "AAPL",
    "微软": "MSFT",
    "microsoft": "MSFT",
    "msft": "MSFT",
    "谷歌": "GOOGL",
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "亚马逊": "AMZN",
    "amazon": "AMZN",
    "amzn": "AMZN",
    "特斯拉": "TSLA",
    "tesla": "TSLA",
    "tsla": "TSLA",
    "英伟达": "NVDA",
    "nvidia": "NVDA",
    "nvda": "NVDA",
    "脸书": "META",
    "meta": "META",
    "facebook": "META",
    "奈飞": "NFLX",
    "netflix": "NFLX",
    "nflx": "NFLX",
    "amd": "AMD",
    "超微": "AMD",
    "英特尔": "INTC",
    "intel": "INTC",
    "台积电": "TSM",
    "tsm": "TSM",
    "阿斯麦": "ASML",
    "asml": "ASML",
    "高通": "QCOM",
    "qcom": "QCOM",
    "博通": "AVGO",
    "avgo": "AVGO",
    "美光": "AMD",
    "arm": "ARM",
    "波音": "BA",
    "boeing": "BA",
    "可口可乐": "KO",
    "coca cola": "KO",
    "星巴克": "SBUX",
    "starbucks": "SBUX",
    "costco": "COST",
    "好市多": "COST",
    "开市客": "COST",
    "沃尔玛": "WMT",
    "walmart": "WMT",
    "迪士尼": "DIS",
    "disney": "DIS",
    "麦当劳": "MCD",
    "mcdonald": "MCD",
    "强生": "JNJ",
    "jnj": "JNJ",
    "宝洁": "PG",
    "pg": "PG",
    "辉瑞": "PFE",
    "pfe": "PFE",
    "礼来": "PFE",
    "诺和诺德": "PFE",
}


def load_extended_alias_map() -> dict:
    """加载 alias_maps.json 并统一成小写键。"""
    alias_map_path = Path(__file__).resolve().parent / "alias_maps.json"
    if not alias_map_path.exists():
        return {}

    try:
        with alias_map_path.open("r", encoding="utf-8") as f:
            raw_map = json.load(f)
        return {str(k).lower(): v for k, v in raw_map.items()}
    except Exception as e:
        print(f"Failed to load extended alias map: {e}")
        return {}