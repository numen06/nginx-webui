"""
统计数据缓存管理工具
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Dict
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.models import StatisticsCache, StatisticsCache5Min
from app.database import SessionLocal


def get_cache_key_5min(time_bucket: Optional[str] = None) -> str:
    """
    生成5分钟数据的缓存键

    Args:
        time_bucket: 时间桶（可选，用于按小时等粒度缓存）

    Returns:
        缓存键字符串
    """
    if time_bucket:
        return f"5min_{time_bucket}"
    else:
        # 使用小时桶（例如：5min_2025-01-15_10）
        now = datetime.now()
        hour_bucket = now.replace(minute=0, second=0, microsecond=0)
        return f"5min_{hour_bucket.strftime('%Y-%m-%d_%H')}"


def get_cache_key(time_range_hours: int, time_bucket: Optional[str] = None) -> str:
    """
    生成缓存键（整数小时范围：1, 24等）

    Args:
        time_range_hours: 时间范围（小时，整数：1, 24等）
        time_bucket: 时间桶（可选，用于按小时/天等粒度缓存）

    Returns:
        缓存键字符串
    """
    if time_bucket:
        # 按时间桶缓存（例如：24_2025-01-15）
        return f"{time_range_hours}_{time_bucket}"
    else:
        # 根据时间范围自动选择合适的时间桶
        now = datetime.now()
        if time_range_hours <= 1:
            # 1小时：使用小时桶（例如：1_2025-01-15_10）
            hour_bucket = now.replace(minute=0, second=0, microsecond=0)
            return f"{time_range_hours}_{hour_bucket.strftime('%Y-%m-%d_%H')}"
        else:
            # 1天及以上：使用天桶（例如：24_2025-01-15）
            day_bucket = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return f"{time_range_hours}_{day_bucket.strftime('%Y-%m-%d')}"


def get_cached_statistics_5min(max_age_minutes: Optional[int] = 5) -> Optional[Dict]:
    """
    从缓存获取5分钟统计数据

    Args:
        max_age_minutes: 缓存最大年龄（分钟），超过此时间则视为过期

    Returns:
        缓存的统计数据，如果不存在或已过期则返回 None
    """
    db = SessionLocal()
    try:
        # 先尝试使用当前时间桶的缓存键
        cache_key = get_cache_key_5min()

        # 查询缓存（优先查找精确匹配的缓存键）
        cache = (
            db.query(StatisticsCache5Min)
            .filter(StatisticsCache5Min.cache_key == cache_key)
            .order_by(StatisticsCache5Min.updated_at.desc())
            .first()
        )

        # 如果没找到，查找最新的缓存（可能时间桶不同）
        if not cache:
            cache = (
                db.query(StatisticsCache5Min)
                .order_by(StatisticsCache5Min.updated_at.desc())
                .first()
            )

        # 调试：如果没找到缓存，记录所有可用的缓存
        if not cache:
            all_caches = db.query(StatisticsCache5Min).all()
            if all_caches:
                print(
                    f"[statistics_cache] 未找到5分钟缓存（cache_key={cache_key}），当前数据库中的5分钟缓存："
                )
                for c in all_caches:
                    print(f"  - cache_key={c.cache_key}, updated_at={c.updated_at}")
            else:
                print(f"[statistics_cache] 数据库中没有任何5分钟缓存数据")
            return None

        # 检查缓存是否过期（如果设置了过期时间）
        if max_age_minutes is not None and max_age_minutes > 0:
            age = datetime.now() - cache.updated_at.replace(tzinfo=None)
            if age > timedelta(minutes=max_age_minutes):
                return None

        # 解析并返回数据
        try:
            return json.loads(cache.data)
        except json.JSONDecodeError:
            return None
    finally:
        db.close()


def get_cached_statistics(
    time_range_hours: int, max_age_minutes: Optional[int] = 5
) -> Optional[Dict]:
    """
    从缓存获取统计数据（整数小时范围：1, 24等）

    Args:
        time_range_hours: 时间范围（小时，整数：1, 24等）
        max_age_minutes: 缓存最大年龄（分钟），超过此时间则视为过期

    Returns:
        缓存的统计数据，如果不存在或已过期则返回 None
    """
    db = SessionLocal()
    try:
        # 确保是整数
        time_range_hours = int(time_range_hours)

        # 先尝试使用当前时间桶的缓存键
        cache_key = get_cache_key(time_range_hours)

        # 查询缓存（优先查找精确匹配的缓存键）
        cache = (
            db.query(StatisticsCache)
            .filter(
                StatisticsCache.cache_key == cache_key,
                StatisticsCache.time_range_hours == time_range_hours,
            )
            .order_by(StatisticsCache.updated_at.desc())
            .first()
        )

        # 如果没找到，查找该时间范围的最新缓存（可能时间桶不同）
        if not cache:
            cache = (
                db.query(StatisticsCache)
                .filter(StatisticsCache.time_range_hours == time_range_hours)
                .order_by(StatisticsCache.updated_at.desc())
                .first()
            )

        # 调试：如果没找到缓存，记录所有可用的缓存
        if not cache:
            all_caches = db.query(StatisticsCache).all()
            if all_caches:
                print(
                    f"[statistics_cache] 未找到 time_range_hours={time_range_hours} 的缓存（cache_key={cache_key}），当前数据库中的缓存："
                )
                for c in all_caches:
                    print(
                        f"  - time_range_hours={c.time_range_hours}, cache_key={c.cache_key}, updated_at={c.updated_at}"
                    )
            else:
                print(f"[statistics_cache] 数据库中没有任何缓存数据")
            return None

        # 检查缓存是否过期（如果设置了过期时间）
        if max_age_minutes is not None and max_age_minutes > 0:
            age = datetime.now() - cache.updated_at.replace(tzinfo=None)
            if age > timedelta(minutes=max_age_minutes):
                return None

        # 解析并返回数据
        try:
            return json.loads(cache.data)
        except json.JSONDecodeError:
            return None
    finally:
        db.close()


def save_statistics_cache_5min(
    data: Dict,
    start_time: datetime,
    end_time: datetime,
    last_log_position: int = 0,
) -> None:
    """
    保存5分钟统计数据到缓存

    Args:
        data: 统计数据字典
        start_time: 统计开始时间
        end_time: 统计结束时间
        last_log_position: 上次读取的日志位置
    """
    db = SessionLocal()
    try:
        cache_key = get_cache_key_5min()

        # 查找现有缓存（按缓存键匹配）
        cache = (
            db.query(StatisticsCache5Min)
            .filter(StatisticsCache5Min.cache_key == cache_key)
            .first()
        )

        # 序列化数据
        data_json = json.dumps(data, default=str)

        if cache:
            # 更新现有缓存
            cache.data = data_json
            cache.start_time = start_time
            cache.end_time = end_time
            cache.last_log_position = last_log_position
            cache.updated_at = datetime.now()
        else:
            # 创建新缓存
            cache = StatisticsCache5Min(
                cache_key=cache_key,
                data=data_json,
                start_time=start_time,
                end_time=end_time,
                last_log_position=last_log_position,
            )
            db.add(cache)

        db.commit()
    except Exception as e:
        db.rollback()
        # 缓存失败不应该影响主流程，只记录错误
        print(f"保存5分钟统计缓存失败: {e}")
    finally:
        db.close()


def save_statistics_cache(
    time_range_hours: int,
    data: Dict,
    start_time: datetime,
    end_time: datetime,
    last_log_position: int = 0,
) -> None:
    """
    保存统计数据到缓存（整数小时范围：1, 24等）

    Args:
        time_range_hours: 时间范围（小时，整数：1, 24等）
        data: 统计数据字典
        start_time: 统计开始时间
        end_time: 统计结束时间
        last_log_position: 上次读取的日志位置
    """
    db = SessionLocal()
    try:
        # 确保是整数
        time_range_hours = int(time_range_hours)
        cache_key = get_cache_key(time_range_hours)

        # 查找现有缓存（按缓存键和时间范围匹配）
        cache = (
            db.query(StatisticsCache)
            .filter(
                StatisticsCache.cache_key == cache_key,
                StatisticsCache.time_range_hours == time_range_hours,
            )
            .first()
        )

        # 序列化数据
        data_json = json.dumps(data, default=str)

        if cache:
            # 更新现有缓存
            cache.data = data_json
            cache.start_time = start_time
            cache.end_time = end_time
            cache.last_log_position = last_log_position
            cache.updated_at = datetime.now()
        else:
            # 创建新缓存
            cache = StatisticsCache(
                time_range_hours=time_range_hours,
                cache_key=cache_key,
                data=data_json,
                start_time=start_time,
                end_time=end_time,
                last_log_position=last_log_position,
            )
            db.add(cache)

        db.commit()
    except Exception as e:
        db.rollback()
        # 缓存失败不应该影响主流程，只记录错误
        print(f"保存统计缓存失败: {e}")
    finally:
        db.close()


def get_last_log_position_5min() -> int:
    """
    获取5分钟数据的上次读取的日志位置

    Returns:
        上次读取的日志行号，如果没有则返回 0
    """
    db = SessionLocal()
    try:
        # 查找最新的缓存
        cache = (
            db.query(StatisticsCache5Min)
            .order_by(StatisticsCache5Min.updated_at.desc())
            .first()
        )

        if cache:
            return cache.last_log_position
        return 0
    finally:
        db.close()


def get_last_log_position(time_range_hours: int) -> int:
    """
    获取上次读取的日志位置（整数小时范围：1, 24等）

    Args:
        time_range_hours: 时间范围（小时，整数：1, 24等）

    Returns:
        上次读取的日志行号，如果没有则返回 0
    """
    db = SessionLocal()
    try:
        # 确保是整数
        time_range_hours = int(time_range_hours)

        # 查找该时间范围的最新缓存
        cache = (
            db.query(StatisticsCache)
            .filter(StatisticsCache.time_range_hours == time_range_hours)
            .order_by(StatisticsCache.updated_at.desc())
            .first()
        )

        if cache:
            return cache.last_log_position
        return 0
    finally:
        db.close()


def cleanup_old_cache(max_age_hours: int = 24) -> None:
    """
    清理过期的缓存记录（包括5分钟缓存和常规缓存）

    Args:
        max_age_hours: 缓存最大保留时间（小时）
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        # 清理常规缓存
        deleted = (
            db.query(StatisticsCache)
            .filter(StatisticsCache.updated_at < cutoff_time)
            .delete()
        )

        # 清理5分钟缓存
        deleted_5min = (
            db.query(StatisticsCache5Min)
            .filter(StatisticsCache5Min.updated_at < cutoff_time)
            .delete()
        )

        db.commit()
        if deleted > 0 or deleted_5min > 0:
            print(f"清理了 {deleted} 条过期统计缓存，{deleted_5min} 条5分钟缓存")
    except Exception as e:
        db.rollback()
        print(f"清理缓存失败: {e}")
    finally:
        db.close()
