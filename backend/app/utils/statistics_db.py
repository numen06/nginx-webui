"""
新的统计数据库操作工具 - 基于时间桶表设计
"""

import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from sqlalchemy import func, and_
from sqlalchemy.orm import Session

from app.models import Statistics5Min, StatisticsHourly, StatisticsDaily
from app.database import SessionLocal


def save_statistics_5min(time_bucket: datetime, data: Dict) -> None:
    """
    保存5分钟粒度统计数据
    
    Args:
        time_bucket: 时间桶（如 2025-12-02 07:00:00 表示7:00-7:05）
        data: 统计数据字典
    """
    db = SessionLocal()
    try:
        # 对齐到5分钟
        minute = (time_bucket.minute // 5) * 5
        time_bucket = time_bucket.replace(minute=minute, second=0, microsecond=0)
        
        # 查找现有记录
        record = db.query(Statistics5Min).filter(
            Statistics5Min.time_bucket == time_bucket
        ).first()
        
        summary = data.get("summary", {})
        
        if record:
            # 更新现有记录
            record.total_requests = summary.get("total_requests", 0)
            record.success_requests = summary.get("success_requests", 0)
            record.error_requests = summary.get("error_requests", 0)
            record.attack_count = summary.get("attack_count", 0)
            record.error_log_count = summary.get("error_log_count", 0)
            record.status_distribution = json.dumps(data.get("status_distribution", {}))
            record.method_distribution = json.dumps(data.get("method_distribution", {}))
            record.top_ips = json.dumps(data.get("top_ips", []))
            record.top_paths = json.dumps(data.get("top_paths", []))
            record.attacks = json.dumps(data.get("attacks", []))
            record.updated_at = datetime.now()
        else:
            # 创建新记录
            record = Statistics5Min(
                time_bucket=time_bucket,
                total_requests=summary.get("total_requests", 0),
                success_requests=summary.get("success_requests", 0),
                error_requests=summary.get("error_requests", 0),
                attack_count=summary.get("attack_count", 0),
                error_log_count=summary.get("error_log_count", 0),
                status_distribution=json.dumps(data.get("status_distribution", {})),
                method_distribution=json.dumps(data.get("method_distribution", {})),
                top_ips=json.dumps(data.get("top_ips", [])),
                top_paths=json.dumps(data.get("top_paths", [])),
                attacks=json.dumps(data.get("attacks", [])),
            )
            db.add(record)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"保存5分钟统计失败: {e}")
    finally:
        db.close()


def query_statistics(hours: int) -> Optional[Dict]:
    """
    查询统计数据（通过SQL聚合）
    
    Args:
        hours: 时间范围（小时）
        
    Returns:
        聚合后的统计数据
    """
    db = SessionLocal()
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        # 只从5分钟表查询（最精细粒度）
        records = db.query(Statistics5Min).filter(
            Statistics5Min.time_bucket >= start_time,
            Statistics5Min.time_bucket <= end_time
        ).order_by(Statistics5Min.time_bucket).all()
        
        if not records:
            return None
        
        # SQL聚合基础指标
        total_requests = sum(r.total_requests for r in records)
        success_requests = sum(r.success_requests for r in records)
        error_requests = sum(r.error_requests for r in records)
        attack_count = sum(r.attack_count for r in records)
        error_log_count = sum(r.error_log_count for r in records)
        
        # 合并详细数据
        status_dist = {}
        method_dist = {}
        ip_counts = {}
        path_counts = {}
        all_attacks = []
        
        for record in records:
            # 合并status_distribution
            if record.status_distribution:
                for status, count in json.loads(record.status_distribution).items():
                    status_dist[status] = status_dist.get(status, 0) + count
            
            # 合并method_distribution
            if record.method_distribution:
                for method, count in json.loads(record.method_distribution).items():
                    method_dist[method] = method_dist.get(method, 0) + count
            
            # 合并top_ips
            if record.top_ips:
                for ip_item in json.loads(record.top_ips):
                    ip = ip_item["ip"]
                    ip_counts[ip] = ip_counts.get(ip, 0) + ip_item["count"]
            
            # 合并top_paths
            if record.top_paths:
                for path_item in json.loads(record.top_paths):
                    path = path_item["path"]
                    path_counts[path] = path_counts.get(path, 0) + path_item["count"]
            
            # 合并attacks
            if record.attacks:
                all_attacks.extend(json.loads(record.attacks))
        
        # 生成top列表
        top_ips = sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        top_paths = sorted(path_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # 生成趋势数据（根据查询时间范围选择粒度）
        trend_hours = []
        trend_counts = []
        
        if hours <= 1:
            # 1小时：5分钟粒度
            for record in records:
                trend_hours.append(record.time_bucket.strftime("%Y-%m-%d %H:%M"))
                trend_counts.append(record.total_requests)
        elif hours <= 24:
            # 24小时：聚合为小时粒度
            hourly_buckets = {}
            for record in records:
                hour_key = record.time_bucket.strftime("%Y-%m-%d %H:00")
                hourly_buckets[hour_key] = hourly_buckets.get(hour_key, 0) + record.total_requests
            for hour_key in sorted(hourly_buckets.keys()):
                trend_hours.append(hour_key)
                trend_counts.append(hourly_buckets[hour_key])
        else:
            # 7天：聚合为天粒度
            daily_buckets = {}
            for record in records:
                day_key = record.time_bucket.strftime("%Y-%m-%d")
                daily_buckets[day_key] = daily_buckets.get(day_key, 0) + record.total_requests
            for day_key in sorted(daily_buckets.keys()):
                trend_hours.append(day_key)
                trend_counts.append(daily_buckets[day_key])
        
        # 计算错误率
        error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "success": True,
            "time_range_hours": hours,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "last_analysis_time": records[-1].updated_at.isoformat() if records else end_time.isoformat(),
            "analyzed_lines": total_requests,
            "summary": {
                "total_requests": total_requests,
                "success_requests": success_requests,
                "error_requests": error_requests,
                "error_rate": round(error_rate, 2),
                "attack_count": attack_count,
                "error_log_count": error_log_count,
            },
            "status_distribution": status_dist,
            "method_distribution": method_dist,
            "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
            "top_paths": [{"path": path, "count": count} for path, count in top_paths],
            "hourly_trend": {
                "hours": trend_hours,
                "counts": trend_counts,
            },
            "attacks": sorted(all_attacks, key=lambda x: x.get("time", ""), reverse=True)[:50],
        }
    except Exception as e:
        print(f"查询统计数据失败: {e}")
        return None
    finally:
        db.close()


def cleanup_old_statistics(days: int = 7) -> None:
    """
    清理旧的统计数据
    
    Args:
        days: 保留最近N天的数据
    """
    db = SessionLocal()
    try:
        cutoff_time = datetime.now() - timedelta(days=days)
        
        # 清理5分钟表
        deleted_5min = db.query(Statistics5Min).filter(
            Statistics5Min.time_bucket < cutoff_time
        ).delete()
        
        # 清理小时表
        deleted_hourly = db.query(StatisticsHourly).filter(
            StatisticsHourly.time_bucket < cutoff_time
        ).delete()
        
        # 清理天表
        deleted_daily = db.query(StatisticsDaily).filter(
            StatisticsDaily.time_bucket < cutoff_time
        ).delete()
        
        db.commit()
        
        print(f"✓ 清理完成：5min={deleted_5min}, hourly={deleted_hourly}, daily={deleted_daily}")
    except Exception as e:
        db.rollback()
        print(f"清理统计数据失败: {e}")
    finally:
        db.close()

