"""
Nginx 状态缓存管理
使用内存缓存，避免频繁查询进程信息
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import threading

# 全局缓存
_cache: Optional[Dict[str, Any]] = None
_cache_lock = threading.Lock()
_cache_expiry: Optional[datetime] = None

# 缓存有效期（秒）
CACHE_TTL = 10  # 10秒缓存，平衡实时性和性能


def get_cached_nginx_status() -> Optional[Dict[str, Any]]:
    """
    从缓存获取 Nginx 状态
    
    Returns:
        缓存的 Nginx 状态，如果不存在或已过期则返回 None
    """
    with _cache_lock:
        if _cache is None or _cache_expiry is None:
            return None
        
        # 检查缓存是否过期
        if datetime.now() > _cache_expiry:
            return None
        
        # 返回缓存的副本（避免外部修改）
        return _cache.copy()


def set_cached_nginx_status(status: Dict[str, Any]) -> None:
    """
    保存 Nginx 状态到缓存
    
    Args:
        status: Nginx 状态字典
    """
    global _cache, _cache_expiry
    
    with _cache_lock:
        _cache = status.copy()
        _cache_expiry = datetime.now() + timedelta(seconds=CACHE_TTL)


def clear_nginx_status_cache() -> None:
    """
    清除 Nginx 状态缓存
    在 Nginx 启动/停止/切换版本时调用
    """
    global _cache, _cache_expiry
    
    with _cache_lock:
        _cache = None
        _cache_expiry = None

