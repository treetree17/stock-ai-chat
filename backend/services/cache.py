"""
缓存管理 - 内存缓存
"""

from datetime import datetime, timedelta

class CacheService:
    """简单的内存缓存服务"""
    
    _cache = {}
    
    @staticmethod
    def set(key: str, value: any, expire_seconds: int = 3600):
        """设置缓存"""
        CacheService._cache[key] = {
            'value': value,
            'expire_time': datetime.now() + timedelta(seconds=expire_seconds)
        }
    
    @staticmethod
    def get(key: str) -> any:
        """获取缓存"""
        if key not in CacheService._cache:
            return None
        
        cache_data = CacheService._cache[key]
        
        # 检查是否过期
        if datetime.now() > cache_data['expire_time']:
            del CacheService._cache[key]
            return None
        
        return cache_data['value']
    
    @staticmethod
    def clear():
        """清空所有缓存"""
        CacheService._cache.clear()
