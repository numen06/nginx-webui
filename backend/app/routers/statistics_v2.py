"""
统计分析模块 V2 - 100%基于新表架构
- 使用 Statistics5Min/Hourly/Daily 表
- 100% SQL 聚合查询
- 无缓存依赖
"""

import logging
import threading
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from collections import Counter

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.models import User
from app.database import get_db
from app.utils.statistics_db import save_statistics_5min, query_statistics
from app.routers.logs import _resolve_access_log_path, _resolve_error_log_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/statistics", tags=["statistics"])


# ==================== 日志解析 ====================
def parse_nginx_access_log(line: str) -> Optional[Dict]:
    """
    解析 Nginx 访问日志行（简化版，使用正则表达式）

    标准格式: IP - - [date] "method path protocol" status size "referer" "user-agent"
    """
    if not line or not line.strip():
        return None

    try:
        # 正则表达式解析
        pattern = (
            r"^(\S+)\s+-\s+-\s+\[([^\]]+)\]\s+"  # IP, date
            r'"(\S+)\s+(\S+)\s+([^"]+)"\s+'  # method, path, protocol
            r"(\d+)\s+(\d+)\s+"  # status, size
            r'"([^"]*)"\s+"([^"]*)"'  # referer, user-agent
        )

        match = re.match(pattern, line.strip())
        if not match:
            return None

        ip, date_str, method, path, protocol, status, size, referer, user_agent = (
            match.groups()
        )

        # 解析时间
        log_time = None
        try:
            # 格式: 02/Dec/2025:21:30:45 +0800
            date_part = date_str.split()[0] if date_str else ""
            if date_part:
                log_time = datetime.strptime(date_part, "%d/%b/%Y:%H:%M:%S")
        except:
            pass

        return {
            "remote_addr": ip,
            "time": log_time,
            "request_method": method,
            "request_path": path,
            "protocol": protocol,
            "status": int(status) if status else 0,
            "body_bytes_sent": size,
            "http_referer": referer if referer != "-" else "",
            "http_user_agent": user_agent if user_agent != "-" else "",
        }
    except Exception as e:
        logger.debug("[statistics_v2] 日志解析失败: %s", str(e))
        return None


# ==================== 状态管理 ====================
class AnalysisStateManager:
    """分析任务状态管理器"""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "is_running": False,
            "last_start_time": None,
            "last_end_time": None,
            "last_error": None,
            "last_success": None,
            "last_trigger": None,
            "last_duration_seconds": 0.0,
            "watcher_enabled": False,
            "current_analyzed_lines": 0,
            "last_analyzed_lines": 0,
        }

    def reset(self):
        """重置状态"""
        with self._lock:
            self._state.update(
                {
                    "is_running": False,
                    "last_start_time": None,
                    "last_end_time": None,
                    "last_error": None,
                    "last_success": None,
                    "last_trigger": None,
                    "last_duration_seconds": 0.0,
                    "watcher_enabled": False,
                    "current_analyzed_lines": 0,
                    "last_analyzed_lines": 0,
                }
            )

    def start_task(self, trigger: str):
        """开始任务"""
        with self._lock:
            self._state["is_running"] = True
            self._state["last_start_time"] = datetime.now()
            self._state["last_trigger"] = trigger
            self._state["current_analyzed_lines"] = 0

    def finish_task(
        self, success: bool, error: Optional[str] = None, analyzed_lines: int = 0
    ):
        """结束任务"""
        with self._lock:
            end_time = datetime.now()
            start_time = self._state.get("last_start_time")
            duration = (end_time - start_time).total_seconds() if start_time else 0.0

            self._state["is_running"] = False
            self._state["last_end_time"] = end_time
            self._state["last_duration_seconds"] = duration
            self._state["last_success"] = success
            self._state["last_error"] = error if not success else None
            self._state["last_analyzed_lines"] = analyzed_lines
            self._state["current_analyzed_lines"] = 0

    def update_progress(self, lines: int):
        """更新进度"""
        with self._lock:
            self._state["current_analyzed_lines"] = lines

    def get_state(self) -> Dict[str, Any]:
        """获取状态"""
        with self._lock:
            return self._state.copy()


_state_manager = AnalysisStateManager()


# ==================== 核心分析函数 ====================
def analyze_logs_simple(
    hours: int = 1, full: bool = False, trigger: str = "manual"
) -> Dict[str, Any]:
    """
    简化的日志分析函数

    Args:
        hours: 分析时间范围（小时）
        full: 是否全量分析
        trigger: 触发来源

    Returns:
        分析结果统计
    """
    # 性能优化：避免频繁触发
    state = _state_manager.get_state()
    if state["is_running"]:
        logger.info("[statistics_v2] 任务正在运行中，跳过本次触发 (trigger=%s)", trigger)
        return {"success": False, "message": "任务正在运行中"}
    
    # 增量分析时，检查距离上次分析的时间间隔，避免过于频繁
    last_end = state.get("last_end_time")
    if last_end and not full:
        seconds_since_last = (datetime.now() - last_end).total_seconds()
        if seconds_since_last < 10:
            logger.info(
                "[statistics_v2] 距离上次分析仅%.1f秒，跳过以避免频繁触发 (trigger=%s)",
                seconds_since_last,
                trigger
            )
            return {"success": False, "message": "分析间隔太短，请稍后再试"}
    
    _state_manager.start_task(trigger)
    access_log_path = Path(_resolve_access_log_path())
    error_log_path = Path(_resolve_error_log_path())

    try:
        # 1. 确定时间范围
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        logger.info(
            "[statistics_v2] 开始分析: hours=%d, full=%s, 时间范围: %s -> %s",
            hours,
            full,
            start_time.strftime("%Y-%m-%d %H:%M"),
            end_time.strftime("%Y-%m-%d %H:%M"),
        )

        # 2. 读取日志
        offset_file = Path(str(access_log_path) + ".offset")
        offset = 0

        if not full and offset_file.exists():
            # 增量：从上次offset开始
            with open(offset_file, "r") as f:
                offset = int(f.read().strip())
            logger.info("[statistics_v2] 增量分析，从offset %d开始", offset)
        else:
            logger.info("[statistics_v2] 全量分析，读取全部日志")

        # 检查文件轮转
        current_size = access_log_path.stat().st_size
        if current_size < offset:
            logger.info("[statistics_v2] 检测到日志轮转，重置offset")
            offset = 0

        # 3. 统计数据结构
        bucket_stats = {}  # {time_bucket: {ip_stats, status_stats, ...}}
        total_lines = 0
        in_range_lines = 0

        # 4. 读取并解析日志
        with open(access_log_path, "r", encoding="utf-8", errors="ignore") as f:
            f.seek(offset)

            for line in f:
                line = line.strip()
                if not line:
                    continue

                total_lines += 1

                # 解析日志
                parsed = parse_nginx_access_log(line)
                if not parsed:
                    continue

                # 检查时间范围
                log_time = parsed.get("time")
                if not log_time or log_time < start_time or log_time > end_time:
                    continue

                in_range_lines += 1

                # 对齐到5分钟时间桶
                minute = (log_time.minute // 5) * 5
                time_bucket = log_time.replace(minute=minute, second=0, microsecond=0)
                bucket_key = time_bucket.strftime("%Y-%m-%d %H:%M")

                # 初始化bucket
                if bucket_key not in bucket_stats:
                    bucket_stats[bucket_key] = {
                        "time_bucket": time_bucket,
                        "ip_stats": Counter(),
                        "status_stats": Counter(),
                        "method_stats": Counter(),
                        "path_stats": Counter(),
                        "attacks": [],
                    }

                bucket = bucket_stats[bucket_key]

                # 累加统计
                bucket["ip_stats"][parsed.get("remote_addr", "unknown")] += 1
                bucket["status_stats"][str(parsed.get("status", 0))] += 1
                bucket["method_stats"][parsed.get("request_method", "unknown")] += 1
                bucket["path_stats"][parsed.get("request_path", "/")] += 1

                # 检测攻击
                if parsed.get("status", 0) in [400, 401, 403, 404]:
                    bucket["attacks"].append(
                        {
                            "time": log_time.isoformat(),
                            "ip": parsed.get("remote_addr", "unknown"),
                            "path": parsed.get("request_path", "/"),
                            "status": parsed.get("status", 0),
                        }
                    )

                # 进度更新
                if total_lines % 10000 == 0:
                    _state_manager.update_progress(in_range_lines)
                    logger.info(
                        "[statistics_v2] 已处理 %d 行，范围内 %d 行",
                        total_lines,
                        in_range_lines,
                    )

            # 保存新offset
            new_offset = f.tell()

        if not full:
            with open(offset_file, "w") as f:
                f.write(str(new_offset))

        logger.info(
            "[statistics_v2] 访问日志读取完成: 总行数=%d, 范围内=%d, offset: %d -> %d",
            total_lines,
            in_range_lines,
            offset,
            new_offset,
        )

        # 4.5. 分析错误日志
        error_log_count = 0
        if error_log_path.exists():
            try:
                with open(error_log_path, "r", encoding="utf-8", errors="ignore") as ef:
                    for line in ef:
                        if not line.strip():
                            continue
                        # 统计错误日志数量
                        if (
                            "[error]" in line
                            or "[crit]" in line
                            or "[alert]" in line
                            or "[emerg]" in line
                        ):
                            error_log_count += 1

                logger.info(
                    "[statistics_v2] 错误日志分析完成: 共 %d 条错误", error_log_count
                )
            except Exception as e:
                logger.warning("[statistics_v2] 错误日志分析失败: %s", str(e))

        # 5. 保存到数据库
        saved_count = 0
        bucket_count = len(bucket_stats) if bucket_stats else 1
        # 将错误日志数量平均分配到各个时间桶（错误日志没有精确时间戳，只能平均）
        error_log_per_bucket = (
            error_log_count // bucket_count if bucket_count > 0 else error_log_count
        )

        logger.info(
            "[statistics_v2] 准备保存: bucket数=%d, 错误日志总数=%d, 每bucket错误=%d",
            bucket_count,
            error_log_count,
            error_log_per_bucket,
        )

        for bucket_key, bucket in bucket_stats.items():
            # 构造数据
            total_requests = sum(bucket["status_stats"].values())
            success_requests = sum(
                count
                for status, count in bucket["status_stats"].items()
                if 200 <= int(status) < 300
            )
            error_requests = total_requests - success_requests
            attack_count = len(bucket["attacks"])

            data = {
                "summary": {
                    "total_requests": total_requests,
                    "success_requests": success_requests,
                    "error_requests": error_requests,
                    "attack_count": attack_count,
                    "error_log_count": error_log_per_bucket,
                },
                "status_distribution": dict(bucket["status_stats"]),
                "method_distribution": dict(bucket["method_stats"]),
                "top_ips": [
                    {"ip": ip, "count": count}
                    for ip, count in bucket["ip_stats"].most_common(10)
                ],
                "top_paths": [
                    {"path": path, "count": count}
                    for path, count in bucket["path_stats"].most_common(10)
                ],
                "attacks": bucket["attacks"][:50],
            }

            # 保存到数据库
            save_statistics_5min(bucket["time_bucket"], data)
            saved_count += 1

        logger.info("[statistics_v2] ✓ 已保存 %d 个5分钟时间桶到数据库", saved_count)

        # 6. 任务完成
        _state_manager.finish_task(success=True, analyzed_lines=in_range_lines)

        return {
            "success": True,
            "analyzed_lines": in_range_lines,
            "saved_buckets": saved_count,
            "time_range": f"{start_time.strftime('%Y-%m-%d %H:%M')} -> {end_time.strftime('%Y-%m-%d %H:%M')}",
        }

    except Exception as e:
        logger.error("[statistics_v2] 分析失败: %s", str(e), exc_info=True)
        _state_manager.finish_task(success=False, error=str(e))
        raise


# ==================== API 接口 ====================
@router.get("/task-status", summary="获取任务状态")
async def get_task_status(current_user: User = Depends(get_current_user)):
    """获取当前分析任务状态"""
    state = _state_manager.get_state()

    # 计算运行时长
    running_duration = 0.0
    if state["is_running"] and state["last_start_time"]:
        running_duration = (datetime.now() - state["last_start_time"]).total_seconds()

    # 决定显示哪个 analyzed_lines
    analyzed_lines = (
        state["current_analyzed_lines"]
        if state["is_running"]
        else state["last_analyzed_lines"]
    )

    return {
        "success": True,
        "is_running": state["is_running"],
        "analyzed_lines": analyzed_lines,
        "last_trigger": state["last_trigger"],
        "last_success": state["last_success"],
        "last_error": state["last_error"],
        "last_duration_seconds": state["last_duration_seconds"],
        "running_duration_seconds": running_duration,
        "watcher_enabled": state["watcher_enabled"],
    }


@router.post("/analyze", summary="手动触发分析")
async def trigger_analyze(
    hours: int = Query(1, ge=1, le=168, description="分析时间范围（小时）"),
    full: bool = Query(False, description="是否全量分析"),
    current_user: User = Depends(get_current_user),
):
    """手动触发统计分析"""
    state = _state_manager.get_state()
    if state["is_running"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前已有分析任务在运行中",
        )

    # 后台执行
    def run_analysis():
        try:
            analyze_logs_simple(hours=hours, full=full, trigger="manual")
        except Exception as e:
            logger.error("[statistics_v2] 后台分析失败: %s", str(e))

    thread = threading.Thread(target=run_analysis, daemon=True)
    thread.start()

    return {
        "success": True,
        "message": f"{'全量' if full else '增量'}分析已启动（{hours}小时）",
    }


@router.get("/summary", summary="获取统计摘要")
async def get_summary(
    hours: int = Query(1, ge=1, le=168, description="时间范围（小时）"),
    current_user: User = Depends(get_current_user),
):
    """获取统计摘要 - 100%从数据库SQL查询"""
    try:
        result = query_statistics(hours)
        if result:
            return result

        return {
            "success": False,
            "time_range_hours": hours,
            "message": "暂无统计数据，请先触发分析",
        }
    except Exception as e:
        logger.error("[statistics_v2] 查询摘要失败: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )


@router.get("/trend", summary="获取趋势数据")
async def get_trend(
    hours: int = Query(24, ge=1, le=168, description="时间范围（小时）"),
    current_user: User = Depends(get_current_user),
):
    """获取趋势数据 - 100%从数据库SQL查询"""
    try:
        result = query_statistics(hours)
        if result and result.get("hourly_trend"):
            return {
                "success": True,
                "time_range_hours": hours,
                "hourly_trend": result["hourly_trend"],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "hourly_trend": {"hours": [], "counts": []},
            "message": "暂无趋势数据",
        }
    except Exception as e:
        logger.error("[statistics_v2] 查询趋势失败: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )


@router.get("/top-ips", summary="获取Top IP")
async def get_top_ips(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """获取访问量前N的IP"""
    try:
        result = query_statistics(hours)
        if result and result.get("top_ips"):
            return {
                "success": True,
                "time_range_hours": hours,
                "top_ips": result["top_ips"][:limit],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "top_ips": [],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )


@router.get("/top-paths", summary="获取Top路径")
async def get_top_paths(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """获取访问量前N的路径"""
    try:
        result = query_statistics(hours)
        if result and result.get("top_paths"):
            return {
                "success": True,
                "time_range_hours": hours,
                "top_paths": result["top_paths"][:limit],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "top_paths": [],
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )


@router.get("/status-distribution", summary="获取状态码分布")
async def get_status_distribution(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
):
    """获取HTTP状态码分布"""
    try:
        result = query_statistics(hours)
        if result and result.get("status_distribution"):
            return {
                "success": True,
                "time_range_hours": hours,
                "status_distribution": result["status_distribution"],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "status_distribution": {},
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )


@router.get("/attacks", summary="获取攻击记录")
async def get_attacks(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """获取可疑攻击记录"""
    try:
        result = query_statistics(hours)
        if result and result.get("attacks") is not None:
            attacks = result.get("attacks") or []
            return {
                "success": True,
                "time_range_hours": hours,
                "attacks": attacks[:limit],
                "total_count": len(attacks),
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "attacks": [],
            "total_count": 0,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"查询失败: {str(e)}",
        )
