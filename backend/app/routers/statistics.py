"""
Nginx 统计路由
提供访问量、错误率、攻击检测等统计数据
"""

from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter, deque
import logging
import re
import threading
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.utils.nginx_versions import get_active_version
from app.utils.statistics_cache import (
    get_cached_statistics,
    save_statistics_cache,
    cleanup_old_cache,
)
from app.routers.logs import (
    _resolve_access_log_path,
    _resolve_error_log_path,
    parse_log_date,
    read_log_file,
)

router = APIRouter(prefix="/api/statistics", tags=["statistics"])

# 攻击特征关键词（可以后续扩展）
ATTACK_PATTERNS = [
    r"(union.*select)",
    r"(select.*from)",
    r"(insert.*into)",
    r"(delete.*from)",
    r"(update.*set)",
    r"(drop.*table)",
    r"(exec.*\(\))",
    r"(script.*>)",
    r"(javascript:)",
    r"(<iframe)",
    r"(\.\.\/)",
    r"(\.\.\\\\)",
    r"(\.\.\/\.\.\/)",
    r"(eval\()",
    r"(base64_decode)",
    r"(phpinfo)",
    r"(system\(\))",
    r"(cmd=)",
    r"(passwd)",
    r"(shadow)",
    r"(\.bashrc)",
    r"(\.ssh)",
    r"(sqlmap)",
    r"(nmap)",
    r"(nikto)",
]


def parse_access_log_line(line: str) -> Optional[Dict]:
    """
    解析 Nginx 访问日志行

    标准格式: IP - - [date] "method path protocol" status size "referer" "user-agent"
    示例: 127.0.0.1 - - [27/Nov/2025:00:27:04 +0800] "GET / HTTP/1.1" 200 579 "-" "Mozilla/5.0..."
    """
    # Nginx 访问日志正则表达式
    pattern = (
        r'^(\S+) - - \[([^\]]+)\] "(\S+) (\S+) ([^"]+)" (\d+) (\S+) "([^"]*)" "([^"]*)"'
    )
    match = re.match(pattern, line)

    if not match:
        return None

    try:
        ip = match.group(1)
        date_str = match.group(2)
        method = match.group(3)
        path = match.group(4)
        protocol = match.group(5)
        status = int(match.group(6))
        size = match.group(7)
        referer = match.group(8)
        user_agent = match.group(9)

        # 解析日期
        try:
            # 格式: 27/Nov/2025:00:27:04 +0800
            date_part = date_str.split()[0]  # 27/Nov/2025:00:27:04
            log_date = datetime.strptime(date_part, "%d/%b/%Y:%H:%M:%S")
        except:
            log_date = None

        return {
            "ip": ip,
            "date": log_date,
            "method": method,
            "path": path,
            "protocol": protocol,
            "status": status,
            "size": size,
            "referer": referer,
            "user_agent": user_agent,
            "raw": line,
        }
    except:
        return None


def detect_attack(log_entry: Dict) -> List[str]:
    """检测可能的攻击特征"""
    attacks = []
    path = log_entry.get("path", "").lower()
    user_agent = log_entry.get("user_agent", "").lower()
    referer = log_entry.get("referer", "").lower()

    # 检查状态码（4xx和5xx可能表示攻击尝试）
    status = log_entry.get("status", 0)
    if status >= 400 and status < 500:
        # 403可能是目录遍历等攻击
        if status == 403:
            attacks.append("可疑访问被拒绝")
        # 404可能是扫描探测
        elif status == 404 and (
            "/admin" in path or "/wp-admin" in path or "/phpmyadmin" in path
        ):
            attacks.append("目录扫描探测")

    # 检查路径中的攻击模式
    text_to_check = path + " " + user_agent + " " + referer
    for pattern in ATTACK_PATTERNS:
        if re.search(pattern, text_to_check, re.IGNORECASE):
            attacks.append(f"检测到攻击模式: {pattern}")

    return attacks


def read_log_tail(file_path: Path, max_lines: int = 2000) -> List[str]:
    """
    读取日志文件的最后N行（优化大文件读取）

    Args:
        file_path: 日志文件路径
        max_lines: 最大读取行数

    Returns:
        日志行列表（从旧到新）
    """
    if not file_path.exists():
        return []

    try:
        # 使用 seek 从文件末尾开始读取，避免读取整个文件
        with open(file_path, "rb") as f:
            # 移动到文件末尾
            f.seek(0, 2)
            file_size = f.tell()

            # 如果文件很小，直接读取全部
            if file_size < 1024 * 1024:  # 小于1MB
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f2:
                    return f2.readlines()

            # 从文件末尾向前读取
            lines = []
            buffer_size = min(8192, file_size)  # 每次读取8KB
            position = file_size
            buffer = b""

            while len(lines) < max_lines and position > 0:
                # 计算要读取的大小
                read_size = min(buffer_size, position)
                position -= read_size

                # 读取数据块
                f.seek(position)
                chunk = f.read(read_size)
                buffer = chunk + buffer

                # 按行分割
                while b"\n" in buffer and len(lines) < max_lines:
                    line, buffer = buffer.rsplit(b"\n", 1)
                    try:
                        lines.insert(0, line.decode("utf-8", errors="ignore") + "\n")
                    except:
                        pass

                # 如果已经读取足够的数据，停止
                if position == 0:
                    # 处理最后一行
                    if buffer:
                        try:
                            lines.insert(
                                0, buffer.decode("utf-8", errors="ignore") + "\n"
                            )
                        except:
                            pass
                    break

            return lines[-max_lines:] if len(lines) > max_lines else lines
    except Exception as e:
        # 如果优化读取失败，回退到简单读取（但仍然只保留最后 max_lines 行，避免一次性读入整个超大文件）
        try:
            from collections import deque as _deque

            tail = _deque(maxlen=max_lines)
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    tail.append(line)
            return list(tail)
        except:
            return []


def _parse_logs_in_range(time_range_hours: int = 24) -> List[Dict]:
    """
    解析指定时间范围内的日志条目（基础函数，只解析不统计）

    Args:
        time_range_hours: 时间范围（小时）

    Returns:
        日志条目列表
    """
    access_log_path = _resolve_access_log_path()

    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=time_range_hours)

    # 优化：只读取最后 N 行日志
    # 约定：每小时最多分析约 1000 行，整体上限为 20,000 行，避免一次性处理过多日志导致内存/CPU 压力过大
    max_lines = min(20000, time_range_hours * 1000)

    # 读取访问日志
    access_log_file = Path(access_log_path)
    all_lines = read_log_tail(access_log_file, max_lines=max_lines)

    # 解析日志
    log_entries = []
    for line in all_lines:
        entry = parse_access_log_line(line.strip())
        if not entry or not entry.get("date"):
            continue

        # 过滤时间范围
        if entry["date"] < start_time:
            continue

        log_entries.append(entry)

    return log_entries


def iter_log_lines_from_tail(file_path: Path):
    """
    从文件尾部开始迭代日志行（从新到旧），按需一行行向前扫描，
    避免一次性加载过多数据到内存。
    """
    if not file_path.exists():
        return

    try:
        with open(file_path, "rb") as f:
            f.seek(0, 2)
            file_size = f.tell()

            # 小文件直接读完再反向遍历
            if file_size < 1024 * 1024:  # < 1MB
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f2:
                    all_lines = [line.rstrip("\n") for line in f2.readlines()]
                    for line in reversed(all_lines):
                        yield line
                return

            buffer_size = min(8192, file_size)
            position = file_size
            buffer = b""

            while position > 0:
                read_size = min(buffer_size, position)
                position -= read_size
                f.seek(position)
                chunk = f.read(read_size)
                buffer = chunk + buffer

                # 从缓冲区尾部开始拆行（从新到旧）
                while b"\n" in buffer:
                    line, buffer = buffer.rsplit(b"\n", 1)
                    try:
                        yield line.decode("utf-8", errors="ignore")
                    except Exception:
                        continue

            # 处理文件开头剩余的一行
            if buffer:
                try:
                    yield buffer.decode("utf-8", errors="ignore")
                except Exception:
                    pass
    except Exception:
        # 回退到简单读取（仍然是从新到旧逐行迭代）
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                all_lines = [line.rstrip("\n") for line in f.readlines()]
                for line in reversed(all_lines):
                    yield line
        except Exception:
            return


logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL_SECONDS = 300  # 后台分析间隔：5分钟

# 全局分析状态（仅用于任务状态展示，而不是数据内容）
ANALYSIS_STATE: Dict[str, Any] = {
    "is_running": False,  # 当前是否有分析任务在执行
    "last_start_time": None,  # 最近一次分析任务开始时间
    "last_end_time": None,  # 最近一次分析任务结束时间
    "last_error": None,  # 最近一次分析错误信息（如果有）
    "last_success": None,  # 最近一次分析是否成功 True/False/None
    "last_trigger": None,  # 最近一次分析触发方式：auto / manual
}


def _run_analyze_in_background(time_range_hours: int, trigger: str = "manual") -> None:
    """在单独线程中运行日志分析，避免阻塞请求线程"""

    def _task():
        try:
            analyze_logs(
                time_range_hours=time_range_hours,
                use_cache=False,
                trigger=trigger,
            )
        except Exception as e:
            ANALYSIS_STATE["last_error"] = str(e)

    # 如果已经在分析中，直接跳过
    if ANALYSIS_STATE.get("is_running"):
        logger.info(
            "[statistics] 后台分析已在进行中，本次触发将被忽略（hours=%s）",
            time_range_hours,
        )
        return

    t = threading.Thread(target=_task, daemon=True)
    t.start()


def analyze_logs(
    time_range_hours: int = 24,
    use_cache: bool = True,
    trigger: str = "auto",
) -> Dict:
    """
    分析日志并返回完整统计数据（保留用于兼容性）

    Args:
        time_range_hours: 时间范围（小时）
        use_cache: 是否使用缓存
    """
    logger.info(
        "[statistics] 开始分析访问日志，time_range_hours=%s, use_cache=%s, trigger=%s",
        time_range_hours,
        use_cache,
        trigger,
    )

    # 尝试从缓存获取
    if use_cache:
        cached_data = get_cached_statistics(time_range_hours, max_age_minutes=5)
        if cached_data:
            logger.info(
                "[statistics] 命中统计缓存，直接返回结果，time_range_hours=%s",
                time_range_hours,
            )
            return cached_data

    access_log_path = _resolve_access_log_path()
    error_log_path = _resolve_error_log_path()

    # 计算时间范围
    end_time = datetime.now()
    start_time = end_time - timedelta(hours=time_range_hours)

    # 标记分析开始（任务级状态）
    ANALYSIS_STATE["is_running"] = True
    ANALYSIS_STATE["last_start_time"] = end_time
    ANALYSIS_STATE["last_error"] = None
    ANALYSIS_STATE["last_success"] = None
    ANALYSIS_STATE["last_trigger"] = trigger

    access_log_file = Path(access_log_path)

    # 解析日志（从尾部开始逐行向前扫描，直到时间边界，不一次性加载所有内容）
    total_requests = 0
    ip_stats: Dict[str, int] = defaultdict(int)
    status_stats: Dict[int, int] = defaultdict(int)
    path_stats: Dict[str, int] = defaultdict(int)
    method_stats: Dict[str, int] = defaultdict(int)
    # 通用时间桶统计（根据 time_range_hours 决定粒度）
    bucket_stats: Dict[str, int] = defaultdict(int)
    attack_count = 0
    attack_details = []
    # 上次分析时间：按“日志中最后一条有效记录的时间”来定义
    last_entry_time: Optional[datetime] = None

    start_ts = datetime.now()

    try:
        for line in iter_log_lines_from_tail(access_log_file):
            entry = parse_access_log_line(line.strip())
            if not entry or not entry.get("date"):
                continue

            # 过滤时间范围
            if entry["date"] < start_time:
                # 因为是从新到旧扫描，遇到早于时间边界的日志后可以直接停止
                break

            total_requests += 1

            # 记录最新的日志时间（用于“上次分析时间”展示）
            if (last_entry_time is None) or (entry["date"] > last_entry_time):
                last_entry_time = entry["date"]

            # 统计IP访问
            ip_stats[entry["ip"]] += 1

            # 统计状态码
            status = entry["status"]
            status_stats[status] += 1

            # 统计路径
            path_stats[entry["path"]] += 1

            # 统计HTTP方法
            method_stats[entry["method"]] += 1

            # 按时间桶统计
            # - 当 time_range_hours <= 1 小时时，按 5 分钟粒度统计
            # - 当 time_range_hours >= 7 天（168 小时）时，按天统计
            # - 其他情况（例如 24 小时）按小时统计
            dt = entry["date"]
            if time_range_hours <= 1:
                # 5 分钟对齐：00,05,10,...,55
                rounded_minute = (dt.minute // 5) * 5
                bucket_dt = dt.replace(minute=rounded_minute, second=0, microsecond=0)
                bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M")
            elif time_range_hours >= 24 * 7:
                # 按天聚合
                bucket_key = dt.strftime("%Y-%m-%d")
            else:
                # 按小时聚合
                bucket_key = dt.strftime("%Y-%m-%d %H:00")

            bucket_stats[bucket_key] += 1

            # 检测攻击
            attacks = detect_attack(entry)
            if attacks:
                attack_count += 1
                attack_details.append(
                    {
                        "time": entry["date"].isoformat(),
                        "ip": entry["ip"],
                        "path": entry["path"],
                        "status": status,
                        "attacks": attacks,
                    }
                )
    except Exception as e:
        ANALYSIS_STATE["last_error"] = str(e)
        ANALYSIS_STATE["last_success"] = False
        logger.exception(
            "[statistics] 日志分析失败，time_range_hours=%s, error=%s",
            time_range_hours,
            e,
        )
        raise
    finally:
        # 标记分析结束
        ANALYSIS_STATE["is_running"] = False
        ANALYSIS_STATE["last_end_time"] = datetime.now()
        duration = (ANALYSIS_STATE["last_end_time"] - start_ts).total_seconds()
        logger.info(
            "[statistics] 日志分析完成，time_range_hours=%s, total_requests=%s, 耗时=%.2fs",
            time_range_hours,
            total_requests,
            duration,
        )

    error_requests = sum(
        count for status, count in status_stats.items() if status >= 400
    )
    success_requests = sum(
        count for status, count in status_stats.items() if 200 <= status < 300
    )

    # 计算错误率
    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

    # 获取访问量前10的IP
    top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 获取访问量前10的路径
    top_paths = sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 按时间排序统计数据
    sorted_buckets = sorted(bucket_stats.items())
    bucket_labels = [item[0] for item in sorted_buckets]
    bucket_counts = [item[1] for item in sorted_buckets]

    # 读取错误日志统计（优化：只读取最后部分）
    error_log_count = 0
    error_log_file = Path(error_log_path)
    if error_log_file.exists():
        try:
            error_lines = read_log_tail(error_log_file, max_lines=10000)
            # 统计最近时间范围内的错误日志
            for line in error_lines:
                log_date = parse_log_date(line)
                if log_date and log_date >= start_time:
                    error_log_count += 1
        except Exception:
            pass

    # 计算状态字段
    # “上次分析时间” = 日志中最后一条被分析记录的时间（如果有），否则回退到分析结束时间
    last_analysis_time = (
        last_entry_time or ANALYSIS_STATE.get("last_end_time") or end_time
    )
    next_analysis_time = None
    if last_analysis_time:
        next_analysis_time = last_analysis_time + timedelta(
            seconds=ANALYSIS_INTERVAL_SECONDS
        )

    result = {
        "success": True,
        "time_range_hours": time_range_hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        # 分析状态相关字段（数据粒度）
        "analysis_status": "success",
        "analysis_status_message": None,
        "is_analyzing": ANALYSIS_STATE.get("is_running", False),
        "last_analysis_time": (
            last_analysis_time.isoformat() if last_analysis_time else None
        ),
        "next_analysis_time": (
            next_analysis_time.isoformat() if next_analysis_time else None
        ),
        "summary": {
            "total_requests": total_requests,
            "success_requests": success_requests,
            "error_requests": error_requests,
            "error_rate": round(error_rate, 2),
            "attack_count": attack_count,
            "error_log_count": error_log_count,
        },
        "status_distribution": dict(status_stats),
        "method_distribution": dict(method_stats),
        "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
        "top_paths": [{"path": path, "count": count} for path, count in top_paths],
        # 为了兼容前端，仍然沿用 hourly_trend 字段名称，
        # 其中 hours 为时间桶标签（可能是 5 分钟 / 小时 / 天）
        "hourly_trend": {
            "hours": bucket_labels,
            "counts": bucket_counts,
        },
        "attacks": attack_details[:50],  # 最多返回50条攻击记录
    }

    # 保存到缓存
    if use_cache:
        try:
            save_statistics_cache(
                time_range_hours=time_range_hours,
                data=result,
                start_time=start_time,
                end_time=end_time,
                last_log_position=0,
            )
        except Exception as e:
            # 缓存失败不影响返回结果
            print(f"保存统计缓存失败: {e}")

    return result


@router.get("/overview", summary="获取统计概览")
async def get_statistics_overview(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    获取 Nginx 统计概览数据

    说明：
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间临时解析日志，避免阻塞和卡死
    """
    try:
        cached = get_cached_statistics(hours, max_age_minutes=30)
        if cached:
            return cached

        # 缓存尚未生成时返回占位结果，提示前端稍后重试
        return {
            "success": False,
            "time_range_hours": hours,
            "message": "统计数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计数据失败: {str(e)}",
        )


@router.get("/realtime", summary="获取实时统计数据")
async def get_realtime_statistics(
    current_user: User = Depends(get_current_user),
):
    """
    获取最近1小时的实时统计数据

    说明：
    - 只返回后台预先分析并缓存好的数据（hours=1）
    - 不在请求期间临时解析日志
    """
    try:
        hours = 1
        cached = get_cached_statistics(hours, max_age_minutes=10)
        if cached:
            return cached

        return {
            "success": False,
            "time_range_hours": hours,
            "message": "实时统计数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时统计数据失败: {str(e)}",
        )


@router.get("/summary", summary="获取基础统计数据")
async def get_statistics_summary(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    获取基础统计数据（总数、成功、错误、错误率等）- 轻量级接口

    说明：
    - 只从缓存读取 summary，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("summary"):
            # 任务级状态（后台分析任务本身的状态）
            last_start = ANALYSIS_STATE.get("last_start_time")
            last_end = ANALYSIS_STATE.get("last_end_time")
            analysis_job = {
                "is_running": ANALYSIS_STATE.get("is_running", False),
                "last_start_time": last_start.isoformat() if last_start else None,
                "last_end_time": last_end.isoformat() if last_end else None,
                "last_error": ANALYSIS_STATE.get("last_error"),
                "last_success": ANALYSIS_STATE.get("last_success"),
                "last_trigger": ANALYSIS_STATE.get("last_trigger"),
            }

            return {
                "success": True,
                "time_range_hours": hours,
                "summary": cached_data["summary"],
                "start_time": cached_data.get("start_time"),
                "end_time": cached_data.get("end_time"),
                # 数据级状态（数据新鲜度）
                "analysis_status": cached_data.get("analysis_status") or "ready",
                "analysis_status_message": cached_data.get("analysis_status_message"),
                "is_analyzing": cached_data.get("is_analyzing", False),
                "last_analysis_time": cached_data.get("last_analysis_time")
                or cached_data.get("end_time"),
                "next_analysis_time": cached_data.get("next_analysis_time"),
                # 任务级状态（供前端展示“后台任务执行状态”）
                "analysis_job": analysis_job,
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "message": "基础统计数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计数据失败: {str(e)}",
        )


@router.post("/analyze", summary="手动触发统计分析")
async def trigger_statistics_analyze(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    手动触发一次统计分析。

    说明：
    - 如果当前已有分析任务在运行，则不会重复触发，直接返回提示。
    - 实际分析在后台线程中执行，不阻塞当前请求。
    """
    # 已在分析中，直接返回提示
    if ANALYSIS_STATE.get("is_running"):
        logger.info(
            "[statistics] 手动触发分析被拒绝：当前已有分析任务在进行中（hours=%s）",
            hours,
        )
        return {
            "success": False,
            "message": "统计分析正在进行中，请稍后再试",
            "is_analyzing": True,
        }

    try:
        logger.info(
            "[statistics] 手动触发统计分析开始，hours=%s，用户=%s",
            hours,
            getattr(current_user, "username", None),
        )
        _run_analyze_in_background(time_range_hours=hours, trigger="manual")
        return {
            "success": True,
            "message": "统计分析已在后台启动",
            "is_analyzing": True,
        }
    except Exception as e:
        logger.exception("[statistics] 手动触发统计分析失败：%s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发统计分析失败: {str(e)}",
        )


@router.get("/trend", summary="获取时间趋势数据")
async def get_statistics_trend(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    获取时间趋势图数据

    说明：
    - 只从缓存读取 hourly_trend，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("hourly_trend"):
            return {
                "success": True,
                "time_range_hours": hours,
                "hourly_trend": cached_data["hourly_trend"],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "message": "趋势数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取趋势数据失败: {str(e)}",
        )


@router.get("/top-ips", summary="获取Top IPs")
async def get_top_ips(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    current_user: User = Depends(get_current_user),
):
    """
    获取访问量Top IPs

    说明：
    - 只从缓存读取 top_ips，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("top_ips"):
            return {
                "success": True,
                "time_range_hours": hours,
                "top_ips": cached_data["top_ips"][:limit],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "top_ips": [],
            "message": "Top IP 数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Top IPs失败: {str(e)}",
        )


@router.get("/top-paths", summary="获取Top Paths")
async def get_top_paths(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    current_user: User = Depends(get_current_user),
):
    """
    获取访问量Top Paths

    说明：
    - 只从缓存读取 top_paths，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("top_paths"):
            return {
                "success": True,
                "time_range_hours": hours,
                "top_paths": cached_data["top_paths"][:limit],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "top_paths": [],
            "message": "Top Path 数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取Top Paths失败: {str(e)}",
        )


@router.get("/status-distribution", summary="获取状态码分布")
async def get_status_distribution(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    current_user: User = Depends(get_current_user),
):
    """
    获取状态码分布数据

    说明：
    - 只从缓存读取 status_distribution，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("status_distribution"):
            return {
                "success": True,
                "time_range_hours": hours,
                "status_distribution": cached_data["status_distribution"],
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "status_distribution": {},
            "message": "状态码分布数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取状态码分布失败: {str(e)}",
        )


@router.get("/attacks", summary="获取攻击检测记录")
async def get_attacks(
    hours: int = Query(
        24, ge=1, le=168, description="统计时间范围（小时），最多168小时（7天）"
    ),
    limit: int = Query(50, ge=1, le=200, description="返回数量"),
    current_user: User = Depends(get_current_user),
):
    """
    获取攻击检测记录（延迟加载，数据量大）

    说明：
    - 只从缓存读取 attacks，不在请求期间重新解析日志
    """
    try:
        cached_data = get_cached_statistics(hours, max_age_minutes=30)
        if cached_data and cached_data.get("attacks") is not None:
            attacks_list = cached_data.get("attacks") or []
            return {
                "success": True,
                "time_range_hours": hours,
                "attacks": attacks_list[:limit],
                "total_count": len(attacks_list),
            }

        return {
            "success": False,
            "time_range_hours": hours,
            "attacks": [],
            "total_count": 0,
            "message": "攻击检测数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取攻击检测记录失败: {str(e)}",
        )
