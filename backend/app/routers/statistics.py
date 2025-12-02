"""
Nginx 统计路由
提供访问量、错误率、攻击检测等统计数据
"""

from typing import Optional, Dict, List, Any
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter, deque
import logging
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.utils.nginx_versions import get_active_version
from app.utils.statistics_cache import (
    get_cached_statistics,
    get_cached_statistics_5min,
    save_statistics_cache,
    save_statistics_cache_5min,
    get_last_log_position,
    get_last_log_position_5min,
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
    使用 pygrok 解析 Nginx 访问日志行

    标准格式（combined）: $remote_addr - $remote_user [$time_local] "$request" $status $body_bytes_sent "$http_referer" "$http_user_agent"
    示例: 127.0.0.1 - - [27/Nov/2025:00:27:04 +0800] "GET / HTTP/1.1" 200 579 "-" "Mozilla/5.0..."
    """
    try:
        from pygrok import Grok

        # Nginx combined 日志格式的 grok 模式
        # 匹配: IP - - [date] "method path protocol" status size "referer" "user-agent"
        grok_pattern = (
            r"%{IPORHOST:remote_addr} - %{USER:remote_user} \[%{HTTPDATE:time_local}\] "
            r'"%{WORD:method} %{URIPATH:path}(?:%{URIPARAM:params})? %{PROG:protocol}" '
            r'%{INT:status} %{INT:body_bytes_sent} "(?:%{URI:referer}|-)" "(?:%{DATA:user_agent}|-)"'
        )

        grok = Grok(grok_pattern)
        match = grok.match(line.strip())

        if not match:
            # 如果 grok 匹配失败，尝试更宽松的模式
            # 处理可能没有 remote_user 的情况（通常是 "-"）
            grok_pattern_fallback = (
                r"%{IPORHOST:remote_addr} (?:%{USER:remote_user}|-) \[%{HTTPDATE:time_local}\] "
                r'"%{WORD:method} %{URIPATH:path}(?:%{URIPARAM:params})? %{PROG:protocol}" '
                r'%{INT:status} %{INT:body_bytes_sent} "(?:%{URI:referer}|-)" "(?:%{DATA:user_agent}|-)"'
            )
            grok_fallback = Grok(grok_pattern_fallback)
            match = grok_fallback.match(line.strip())

        if not match:
            logger.debug("[statistics] 日志行解析失败（pygrok）: %s", line[:100])
            return None

        # 提取字段
        ip = match.get("remote_addr", "").strip()
        date_str = match.get("time_local", "").strip()
        method = match.get("method", "").strip()
        path = match.get("path", "").strip()
        params = match.get("params", "").strip()
        protocol = match.get("protocol", "").strip()
        status = int(match.get("status", 0))
        size = match.get("body_bytes_sent", "0").strip()
        referer = match.get("referer", "-").strip()
        user_agent = match.get("user_agent", "-").strip()

        # 合并路径和参数
        if params:
            full_path = path + params
        else:
            full_path = path

        # 解析日期
        log_date = None
        try:
            # HTTPDATE 格式: 27/Nov/2025:00:27:04 +0800
            # 提取日期部分（去掉时区）
            date_part = date_str.split()[0] if date_str else ""
            if date_part:
                log_date = datetime.strptime(date_part, "%d/%b/%Y:%H:%M:%S")
        except Exception as e:
            logger.debug("[statistics] 日期解析失败: %s, error=%s", date_str, e)
            log_date = None

        # 验证 IP 地址格式（确保不是单个数字）
        if (
            ip
            and not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip)
            and not re.match(r"^[0-9a-fA-F:]+$", ip)
        ):
            # 如果不是有效的 IP 格式，可能是解析错误
            logger.warning(
                "[statistics] 解析到的 IP 格式异常: %s, 原始行: %s", ip, line[:100]
            )
            return None

        return {
            "ip": ip,
            "date": log_date,
            "method": method,
            "path": full_path,
            "protocol": protocol,
            "status": status,
            "size": size,
            "referer": referer if referer != "-" else "",
            "user_agent": user_agent if user_agent != "-" else "",
            "raw": line,
        }
    except ImportError:
        # 如果没有安装 pygrok，回退到正则表达式解析
        logger.warning("[statistics] pygrok 未安装，使用正则表达式解析（可能不够准确）")
        return _parse_access_log_line_regex(line)
    except Exception as e:
        logger.debug("[statistics] pygrok 解析失败，尝试正则表达式: %s", e)
        return _parse_access_log_line_regex(line)


def _parse_access_log_line_regex(line: str) -> Optional[Dict]:
    """
    使用正则表达式解析 Nginx 访问日志行（回退方案）
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

        # 验证 IP 地址格式
        if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip) and not re.match(
            r"^[0-9a-fA-F:]+$", ip
        ):
            logger.warning("[statistics] 正则解析到的 IP 格式异常: %s", ip)
            return None

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


def iter_log_lines_from_tail(
    file_path: Path, use_pygtail: bool = True, full: bool = False
):
    """
    使用 pygtail 进行增量读取日志行，或从文件尾部开始迭代（全量分析时）。

    Args:
        file_path: 日志文件路径
        use_pygtail: 是否使用 pygtail 进行增量读取（默认 True）
        full: 是否全量分析（True=从文件尾部读取整个文件，False=使用 pygtail 增量读取）

    Yields:
        日志行（从新到旧的顺序）
    """
    if not file_path.exists():
        return

    # 全量分析：从文件尾部开始读取整个文件（从新到旧）
    # 使用流式处理，避免大文件导致内存问题
    if full:
        try:
            with open(file_path, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()

                logger.info(
                    "[statistics] 全量分析：开始读取日志文件，大小=%.2f MB",
                    file_size / (1024 * 1024),
                )

                # 小文件（<10MB）直接读完再反向遍历
                if file_size < 10 * 1024 * 1024:  # < 10MB
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f2:
                        all_lines = [line.rstrip("\n") for line in f2.readlines()]
                        logger.info(
                            "[statistics] 全量分析：小文件模式，总行数=%s",
                            len(all_lines),
                        )
                        for line in reversed(all_lines):
                            yield line
                    return

                # 大文件：使用缓冲区流式读取（从尾部向前）
                # 使用更大的缓冲区以提高性能
                buffer_size = min(64 * 1024, file_size)  # 64KB 缓冲区
                position = file_size
                buffer = b""
                # 使用 deque 存储最近的行，避免内存问题
                from collections import deque

                line_buffer = deque(maxlen=10000)  # 最多缓存 10000 行

                lines_yielded = 0
                while position > 0:
                    read_size = min(buffer_size, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    buffer = chunk + buffer

                    # 处理缓冲区中的完整行
                    while True:
                        last_newline = buffer.rfind(b"\n")
                        if last_newline == -1:
                            break

                        line_bytes = buffer[last_newline + 1 :]
                        buffer = buffer[:last_newline]

                        if line_bytes:
                            try:
                                line = line_bytes.decode(
                                    "utf-8", errors="ignore"
                                ).rstrip("\n\r")
                                if line:
                                    line_buffer.appendleft(
                                        line
                                    )  # 从左侧添加，保持从新到旧的顺序
                                    # 当缓冲区满了，yield 一部分行
                                    if len(line_buffer) >= 10000:
                                        for _ in range(5000):  # 每次 yield 5000 行
                                            if line_buffer:
                                                yield line_buffer.popleft()
                                                lines_yielded += 1
                            except Exception:
                                continue

                        if not buffer or b"\n" not in buffer:
                            break

                    # 每处理 100MB 数据，输出一次进度
                    if (file_size - position) % (100 * 1024 * 1024) < buffer_size:
                        logger.info(
                            "[statistics] 全量分析进度：已读取 %.1f%% (%.2f MB / %.2f MB), 已处理行数=%s",
                            (file_size - position) / file_size * 100,
                            (file_size - position) / (1024 * 1024),
                            file_size / (1024 * 1024),
                            lines_yielded,
                        )

                # 处理文件开头剩余的一行
                if buffer:
                    try:
                        line = buffer.decode("utf-8", errors="ignore").rstrip("\n\r")
                        if line:
                            line_buffer.appendleft(line)
                    except Exception:
                        pass

                # Yield 剩余的行
                while line_buffer:
                    yield line_buffer.popleft()
                    lines_yielded += 1

                logger.info(
                    "[statistics] 全量分析：读取完成，总行数=%s",
                    lines_yielded,
                )

        except Exception as e:
            logger.warning("[statistics] 全量读取失败，回退到简单读取: %s", e)
            try:
                # 回退：对于超大文件，使用逐行读取（从新到旧）
                logger.info("[statistics] 全量分析：使用回退模式（逐行读取）")
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    # 使用 deque 限制内存使用
                    from collections import deque

                    tail_lines = deque(maxlen=100000)  # 最多缓存 10 万行
                    for line in f:
                        tail_lines.append(line.rstrip("\n"))
                        if len(tail_lines) >= 100000:
                            # 当缓存满了，yield 一部分
                            for _ in range(50000):
                                if tail_lines:
                                    yield tail_lines.popleft()
                    # Yield 剩余的行
                    while tail_lines:
                        yield tail_lines.popleft()
            except Exception as e2:
                logger.error("[statistics] 回退读取也失败: %s", e2)
                return
        return

    # 增量分析：使用 pygtail 从上次位置读取新内容
    if use_pygtail:
        try:
            from pygtail import Pygtail

            # pygtail 会从上次读取位置开始读取新内容（从旧到新）
            # 增量分析时保持从旧到新的顺序，这样时间过滤逻辑更简单
            tail = Pygtail(
                str(file_path),
                encoding="utf-8",
                errors="ignore",
                copytruncate=True,  # 支持日志轮转
            )

            # 直接yield，保持从旧到新的顺序
            for line in tail:
                line = line.rstrip("\n\r")
                if line:  # 只处理非空行
                    yield line

        except ImportError:
            logger.warning("[statistics] pygtail 未安装，回退到从尾部读取方式")
            use_pygtail = False
        except Exception as e:
            logger.warning("[statistics] pygtail 读取失败，回退到从尾部读取方式: %s", e)
            use_pygtail = False

    # 回退：如果 pygtail 不可用，使用从尾部读取的方式
    if not use_pygtail:
        try:
            with open(file_path, "rb") as f:
                f.seek(0, 2)
                file_size = f.tell()

                if file_size < 1024 * 1024:  # < 1MB
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f2:
                        all_lines = [line.rstrip("\n") for line in f2.readlines()]
                        for line in reversed(all_lines):
                            yield line
                    return

                buffer_size = min(8192, file_size)
                position = file_size
                buffer = b""
                complete_lines = []

                while position > 0:
                    read_size = min(buffer_size, position)
                    position -= read_size
                    f.seek(position)
                    chunk = f.read(read_size)
                    buffer = chunk + buffer

                    while True:
                        last_newline = buffer.rfind(b"\n")
                        if last_newline == -1:
                            break

                        line_bytes = buffer[last_newline + 1 :]
                        buffer = buffer[:last_newline]

                        if line_bytes:
                            try:
                                line = line_bytes.decode(
                                    "utf-8", errors="ignore"
                                ).rstrip("\n\r")
                                if line:
                                    complete_lines.append(line)
                            except Exception:
                                continue

                        if not buffer or b"\n" not in buffer:
                            break

                if buffer:
                    try:
                        line = buffer.decode("utf-8", errors="ignore").rstrip("\n\r")
                        if line:
                            complete_lines.append(line)
                    except Exception:
                        pass

                for line in reversed(complete_lines):
                    yield line

        except Exception as e:
            logger.warning("[statistics] 回退读取失败: %s", e)
            return


logger = logging.getLogger(__name__)

ANALYSIS_INTERVAL_SECONDS = 300  # 后台分析间隔：5分钟


class AnalysisStateManager:
    """统一的分析任务状态管理器 - 简化状态管理逻辑，确保状态一致性"""

    def __init__(self):
        self._task_counter = 0
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
            "current_last_entry_time": None,
            "current_analyzed_lines": 0,
            "last_analyzed_lines": 0,
        }

    def reset(self):
        """重置所有状态（重启时调用）"""
        with self._lock:
            self._task_counter = 0
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
                    "current_last_entry_time": None,
                    "current_analyzed_lines": 0,
                    "last_analyzed_lines": 0,
                }
            )

    def start_task(self, trigger: str):
        """任务开始：增加计数器并更新状态"""
        with self._lock:
            self._task_counter += 1
            self._state["is_running"] = True
            self._state["last_start_time"] = datetime.now()
            self._state["last_error"] = None
            self._state["last_success"] = None
            self._state["last_trigger"] = trigger
            self._state["current_last_entry_time"] = None
            self._state["current_analyzed_lines"] = 0

    def finish_task(
        self, success: bool, error: Optional[str] = None, analyzed_lines: int = 0
    ):
        """任务结束：减少计数器并更新状态"""
        with self._lock:
            if self._task_counter > 0:
                self._task_counter -= 1

            end_time = datetime.now()
            start_time = self._state.get("last_start_time")
            duration = (end_time - start_time).total_seconds() if start_time else 0.0

            self._state["last_end_time"] = end_time
            self._state["last_duration_seconds"] = duration
            self._state["last_success"] = success
            self._state["last_error"] = error if not success else None
            if analyzed_lines > 0:
                self._state["last_analyzed_lines"] = analyzed_lines

            # 如果所有任务都完成了，清除运行状态
            if self._task_counter == 0:
                self._state["is_running"] = False
                self._state["current_last_entry_time"] = None
                self._state["current_analyzed_lines"] = 0

    def update_progress(self, last_entry_time: Optional[datetime], analyzed_lines: int):
        """更新实时进度"""
        with self._lock:
            if self._state["is_running"]:
                self._state["current_last_entry_time"] = last_entry_time
                self._state["current_analyzed_lines"] = analyzed_lines

    def get_state(self) -> Dict[str, Any]:
        """获取当前状态（只读）"""
        with self._lock:
            return self._state.copy()

    def get(self, key: str, default: Any = None) -> Any:
        """获取状态中的某个值"""
        with self._lock:
            return self._state.get(key, default)

    def set_watcher_enabled(self, enabled: bool):
        """设置监听器状态"""
        with self._lock:
            self._state["watcher_enabled"] = enabled

    @property
    def is_running(self) -> bool:
        """是否正在运行"""
        with self._lock:
            return self._state["is_running"]

    @property
    def task_counter(self) -> int:
        """当前任务计数"""
        with self._lock:
            return self._task_counter


# 全局状态管理器实例
_state_manager = AnalysisStateManager()


# 兼容性：导出 ANALYSIS_STATE 作为属性访问器（只读）
class _StateProxy:
    """状态代理类，提供字典式访问，但实际读取自状态管理器"""

    def get(self, key: str, default: Any = None):
        return _state_manager.get(key, default)

    def __getitem__(self, key: str):
        value = _state_manager.get(key)
        if value is None:
            raise KeyError(key)
        return value

    def __contains__(self, key: str):
        return _state_manager.get(key) is not None


ANALYSIS_STATE = _StateProxy()

# 任务组管理：用于统一管理多个子任务（5分钟、1小时、1天）
_task_groups: Dict[str, Dict[str, Any]] = (
    {}
)  # {task_group_id: {total: 3, completed: 0, failed: 0, errors: []}}
_task_groups_lock = threading.Lock()


def _create_task_group(total_tasks: int, trigger: str, full: bool) -> str:
    """创建任务组，返回任务组ID"""
    import uuid

    task_group_id = str(uuid.uuid4())
    with _task_groups_lock:
        _task_groups[task_group_id] = {
            "total": total_tasks,
            "completed": 0,
            "failed": 0,
            "errors": [],
            "trigger": trigger,
            "full": full,
            "start_time": datetime.now(),
        }
    return task_group_id


def _notify_task_group_complete(
    task_group_id: str, success: bool = True, error: Optional[str] = None
):
    """通知任务组某个子任务完成"""
    with _task_groups_lock:
        if task_group_id not in _task_groups:
            logger.warning(
                "[statistics] 任务组不存在：task_group_id=%s, success=%s",
                task_group_id[:8] if task_group_id else "None",
                success,
            )
            return

        group = _task_groups[task_group_id]
        if success:
            group["completed"] += 1
        else:
            group["failed"] += 1
            if error:
                group["errors"].append(error)

        logger.debug(
            "[statistics] 任务组进度更新：task_group_id=%s, 完成=%s/%s, 失败=%s",
            task_group_id[:8],
            group["completed"],
            group["total"],
            group["failed"],
        )

        # 检查是否所有任务都完成了
        total_done = group["completed"] + group["failed"]
        if total_done >= group["total"]:
            # 所有任务完成，更新全局状态
            all_success = group["failed"] == 0
            error_msg = (
                None
                if all_success
                else ("; ".join(group["errors"]) if group["errors"] else "部分任务失败")
            )

            # 获取最终的分析行数（从最新的缓存中获取）
            analyzed_lines = 0
            from app.utils.statistics_cache import (
                get_cached_statistics_5min,
                get_cached_statistics,
            )

            cached_5min = get_cached_statistics_5min(max_age_minutes=None)
            if cached_5min:
                analyzed_lines = cached_5min.get("analyzed_lines", 0)
            else:
                cached_1hr = get_cached_statistics(1, max_age_minutes=None)
                if cached_1hr:
                    analyzed_lines = cached_1hr.get("analyzed_lines", 0)

            # 统一使用状态管理器更新状态
            _state_manager.finish_task(
                success=all_success, error=error_msg, analyzed_lines=analyzed_lines
            )

            logger.info(
                "[statistics] 分析任务组完成：task_group_id=%s, 成功=%s/%s, 失败=%s, 耗时=%.2fs, is_running=%s, task_counter=%s",
                task_group_id[:8],
                group["completed"],
                group["total"],
                group["failed"],
                _state_manager.get("last_duration_seconds", 0),
                _state_manager.is_running,
                _state_manager.task_counter,
            )

            # 清理任务组
            del _task_groups[task_group_id]
        else:
            logger.debug(
                "[statistics] 任务组未完成：task_group_id=%s, 已完成=%s/%s",
                task_group_id[:8],
                total_done,
                group["total"],
            )


def _aggregate_from_5min_cache(
    time_range_hours: int = 1,
    end_time: Optional[datetime] = None,
    update_start_time: Optional[datetime] = None,
) -> Optional[Dict]:
    """
    从5分钟缓存数据聚合生成1小时统计数据（支持增量更新）

    Args:
        time_range_hours: 目标时间范围（小时，通常为1）
        end_time: 结束时间，默认为当前时间
        update_start_time: 增量更新的开始时间（如果提供，只更新此时间之后的数据）

    Returns:
        聚合后的统计数据，如果5分钟缓存不存在则返回 None
    """
    if end_time is None:
        end_time = datetime.now()

    # 如果提供了增量更新的开始时间，只更新该时间之后的数据
    # 否则更新整个时间范围
    if update_start_time:
        start_time = update_start_time
        logger.info(
            "[statistics] 增量聚合1小时数据：只更新 %s 之后的数据",
            update_start_time.isoformat(),
        )
    else:
        start_time = end_time - timedelta(hours=time_range_hours)

    # 获取所有5分钟缓存数据
    cached_5min = get_cached_statistics_5min(max_age_minutes=None)
    if not cached_5min:
        logger.warning("[statistics] 无法从5分钟缓存聚合：未找到5分钟缓存数据")
        return None

    # 解析5分钟缓存的时间范围
    cache_start = datetime.fromisoformat(
        cached_5min.get("start_time", "").replace("Z", "+00:00")
    )
    cache_end = datetime.fromisoformat(
        cached_5min.get("end_time", "").replace("Z", "+00:00")
    )
    if cache_start.tzinfo:
        cache_start = cache_start.replace(tzinfo=None)
    if cache_end.tzinfo:
        cache_end = cache_end.replace(tzinfo=None)

    # 检查缓存数据是否覆盖所需时间范围
    if cache_end < start_time:
        logger.warning(
            "[statistics] 5分钟缓存数据过旧，无法聚合：缓存结束时间=%s, 需要开始时间=%s",
            cache_end.isoformat(),
            start_time.isoformat(),
        )
        return None

    # 获取历史1小时缓存数据（用于合并）
    previous_1hr_cache = get_cached_statistics(1, max_age_minutes=None)

    # 初始化统计数据
    ip_stats: Dict[str, int] = defaultdict(int)
    status_stats: Dict[int, int] = defaultdict(int)
    path_stats: Dict[str, int] = defaultdict(int)
    method_stats: Dict[str, int] = defaultdict(int)
    bucket_stats: Dict[str, int] = defaultdict(int)
    attack_count = 0
    attack_details: List[Dict[str, Any]] = []
    total_requests = 0

    # 如果有历史1小时缓存，先加载历史数据（只加载更新范围之前的数据）
    if previous_1hr_cache and update_start_time:
        prev_trend = previous_1hr_cache.get("hourly_trend", {})
        prev_hours = prev_trend.get("hours", [])
        prev_counts = prev_trend.get("counts", [])

        # 加载更新范围之前的历史数据
        for i, hour_label in enumerate(prev_hours):
            try:
                hour_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:00")
                if hour_dt < update_start_time:
                    bucket_stats[hour_label] = (
                        prev_counts[i] if i < len(prev_counts) else 0
                    )
                    total_requests += bucket_stats[hour_label]
            except Exception:
                continue

        # 合并历史top数据
        for ip_item in previous_1hr_cache.get("top_ips", []):
            ip_stats[ip_item["ip"]] += ip_item["count"]
        for path_item in previous_1hr_cache.get("top_paths", []):
            path_stats[path_item["path"]] += path_item["count"]
        for status_str, count in previous_1hr_cache.get(
            "status_distribution", {}
        ).items():
            status_stats[int(status_str)] += count
        for method, count in previous_1hr_cache.get("method_distribution", {}).items():
            method_stats[method] += count
        attack_count += previous_1hr_cache.get("summary", {}).get("attack_count", 0)
        prev_attacks = previous_1hr_cache.get("attacks", [])
        attack_details.extend(prev_attacks)

        logger.info(
            "[statistics] 已加载历史1小时缓存数据：时间桶数=%s, 总请求数=%s",
            len(bucket_stats),
            total_requests,
        )

    # 从5分钟缓存的时间趋势数据中聚合（只聚合更新范围内的数据）
    hourly_trend = cached_5min.get("hourly_trend", {})
    trend_hours = hourly_trend.get("hours", [])
    trend_counts = hourly_trend.get("counts", [])

    # 过滤时间范围内的数据
    filtered_buckets = {}
    for i, hour_label in enumerate(trend_hours):
        try:
            # 5分钟粒度：YYYY-MM-DD HH:MM
            bucket_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:%M")
            if start_time <= bucket_dt <= end_time:
                filtered_buckets[hour_label] = (
                    trend_counts[i] if i < len(trend_counts) else 0
                )
                total_requests += filtered_buckets[hour_label]
        except Exception:
            continue

    # 按小时聚合（将5分钟数据聚合为小时数据）
    hourly_buckets: Dict[str, int] = defaultdict(int)
    for bucket_key, count in filtered_buckets.items():
        try:
            bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d %H:%M")
            hour_key = bucket_dt.strftime("%Y-%m-%d %H:00")
            hourly_buckets[hour_key] += count
        except Exception:
            continue

    # 合并新聚合的小时数据到bucket_stats
    for hour_key, count in hourly_buckets.items():
        bucket_stats[hour_key] = count  # 覆盖更新范围内的数据

    # 从5分钟缓存的top数据中聚合（增量更新：只更新范围内的数据）
    # 注意：对于增量更新，我们需要合并新数据和历史数据
    # 但由于top数据是全局的，我们需要重新计算top
    top_ips_5min = cached_5min.get("top_ips", [])
    top_paths_5min = cached_5min.get("top_paths", [])
    status_dist_5min = cached_5min.get("status_distribution", {})
    method_dist_5min = cached_5min.get("method_distribution", {})
    attacks_5min = cached_5min.get("attacks", [])

    # 合并IP统计（增量更新时，历史数据已加载，这里只添加新数据）
    if not update_start_time or not previous_1hr_cache:
        # 全量更新：直接使用5分钟数据
        for ip_item in top_ips_5min:
            ip_stats[ip_item["ip"]] = ip_item["count"]  # 覆盖而不是累加
    else:
        # 增量更新：累加新数据
        for ip_item in top_ips_5min:
            ip_stats[ip_item["ip"]] += ip_item["count"]

    # 合并路径统计
    if not update_start_time or not previous_1hr_cache:
        for path_item in top_paths_5min:
            path_stats[path_item["path"]] = path_item["count"]
    else:
        for path_item in top_paths_5min:
            path_stats[path_item["path"]] += path_item["count"]

    # 合并状态码统计
    for status_str, count in status_dist_5min.items():
        if not update_start_time or not previous_1hr_cache:
            status_stats[int(status_str)] = count
        else:
            status_stats[int(status_str)] += count

    # 合并方法统计
    for method, count in method_dist_5min.items():
        if not update_start_time or not previous_1hr_cache:
            method_stats[method] = count
        else:
            method_stats[method] += count

    # 合并攻击记录
    if not update_start_time or not previous_1hr_cache:
        attack_count = cached_5min.get("summary", {}).get("attack_count", 0)
        attack_details = attacks_5min[:50]
    else:
        attack_count += cached_5min.get("summary", {}).get("attack_count", 0)
        # 合并攻击记录，保留最近的
        attack_details = (attack_details + attacks_5min)[:50]

    # 计算汇总统计
    error_requests = sum(
        count for status, count in status_stats.items() if status >= 400
    )
    success_requests = sum(
        count for status, count in status_stats.items() if 200 <= status < 300
    )
    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

    # 获取top数据
    top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    top_paths = sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 按时间排序
    sorted_buckets = sorted(bucket_stats.items())
    bucket_labels = [item[0] for item in sorted_buckets]
    bucket_counts = [item[1] for item in sorted_buckets]

    # 获取错误日志统计（从5分钟缓存中获取）
    error_log_count = cached_5min.get("summary", {}).get("error_log_count", 0)

    result = {
        "success": True,
        "time_range_hours": time_range_hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "analysis_status": "success",
        "analysis_status_message": None,
        "is_analyzing": False,  # 分析完成时，is_analyzing 应该为 False
        "last_analysis_time": cached_5min.get("last_analysis_time"),
        "analyzed_lines": total_requests,
        "summary": {
            "total_requests": total_requests,
            "success_requests": success_requests,
            "error_requests": error_requests,
            "error_rate": round(error_rate, 2),
            "attack_count": attack_count,
            "error_log_count": error_log_count,
        },
        "status_distribution": {str(k): v for k, v in status_stats.items()},
        "method_distribution": dict(method_stats),
        "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
        "top_paths": [{"path": path, "count": count} for path, count in top_paths],
        "hourly_trend": {
            "hours": bucket_labels,
            "counts": bucket_counts,
        },
        "attacks": attack_details,
    }

    logger.info(
        "[statistics] 从5分钟缓存聚合完成：time_range_hours=%s, total_requests=%s, 时间桶数=%s",
        time_range_hours,
        total_requests,
        len(bucket_labels),
    )

    return result


def _aggregate_from_1hour_cache(
    time_range_hours: int = 24,
    end_time: Optional[datetime] = None,
    update_start_time: Optional[datetime] = None,
) -> Optional[Dict]:
    """
    从1小时缓存数据聚合生成1天统计数据（支持增量更新）

    Args:
        time_range_hours: 目标时间范围（小时，通常为24）
        end_time: 结束时间，默认为当前时间
        update_start_time: 增量更新的开始时间（如果提供，只更新此时间之后的数据）

    Returns:
        聚合后的统计数据，如果1小时缓存不存在则返回 None
    """
    if end_time is None:
        end_time = datetime.now()

    # 如果提供了增量更新的开始时间，只更新该时间之后的数据
    # 否则更新整个时间范围
    if update_start_time:
        start_time = update_start_time
        logger.info(
            "[statistics] 增量聚合1天数据：只更新 %s 之后的数据",
            update_start_time.isoformat(),
        )
    else:
        start_time = end_time - timedelta(hours=time_range_hours)

    # 获取1小时缓存数据
    cached_1hr = get_cached_statistics(1, max_age_minutes=None)
    if not cached_1hr:
        logger.warning(
            "[statistics] 无法从1小时缓存聚合：未找到1小时缓存数据，尝试从5分钟缓存聚合"
        )
        # 如果1小时缓存不存在，尝试从5分钟缓存聚合
        return _aggregate_from_5min_cache(time_range_hours, end_time, update_start_time)

    # 获取历史1天缓存数据（用于合并）
    previous_1day_cache = get_cached_statistics(24, max_age_minutes=None)

    # 解析1小时缓存的时间范围
    cache_start = datetime.fromisoformat(
        cached_1hr.get("start_time", "").replace("Z", "+00:00")
    )
    cache_end = datetime.fromisoformat(
        cached_1hr.get("end_time", "").replace("Z", "+00:00")
    )
    if cache_start.tzinfo:
        cache_start = cache_start.replace(tzinfo=None)
    if cache_end.tzinfo:
        cache_end = cache_end.replace(tzinfo=None)

    # 检查缓存数据是否覆盖所需时间范围
    if cache_end < start_time:
        logger.warning(
            "[statistics] 1小时缓存数据过旧，无法聚合：缓存结束时间=%s, 需要开始时间=%s",
            cache_end.isoformat(),
            start_time.isoformat(),
        )
        return None

    # 初始化统计数据
    ip_stats: Dict[str, int] = defaultdict(int)
    status_stats: Dict[int, int] = defaultdict(int)
    path_stats: Dict[str, int] = defaultdict(int)
    method_stats: Dict[str, int] = defaultdict(int)
    bucket_stats: Dict[str, int] = defaultdict(int)
    attack_count = 0
    attack_details: List[Dict[str, Any]] = []
    total_requests = 0

    # 如果有历史1天缓存，先加载历史数据（只加载更新范围之前的数据）
    if previous_1day_cache and update_start_time:
        prev_trend = previous_1day_cache.get("hourly_trend", {})
        prev_days = prev_trend.get("hours", [])
        prev_counts = prev_trend.get("counts", [])

        # 加载更新范围之前的历史数据
        update_start_date = update_start_time.date() if update_start_time else None
        for i, day_label in enumerate(prev_days):
            try:
                day_dt = datetime.strptime(day_label, "%Y-%m-%d").date()
                if update_start_date and day_dt < update_start_date:
                    bucket_stats[day_label] = (
                        prev_counts[i] if i < len(prev_counts) else 0
                    )
                    total_requests += bucket_stats[day_label]
            except Exception:
                continue

        # 合并历史top数据
        for ip_item in previous_1day_cache.get("top_ips", []):
            ip_stats[ip_item["ip"]] += ip_item["count"]
        for path_item in previous_1day_cache.get("top_paths", []):
            path_stats[path_item["path"]] += path_item["count"]
        for status_str, count in previous_1day_cache.get(
            "status_distribution", {}
        ).items():
            status_stats[int(status_str)] += count
        for method, count in previous_1day_cache.get("method_distribution", {}).items():
            method_stats[method] += count
        attack_count += previous_1day_cache.get("summary", {}).get("attack_count", 0)
        prev_attacks = previous_1day_cache.get("attacks", [])
        attack_details.extend(prev_attacks)

        logger.info(
            "[statistics] 已加载历史1天缓存数据：时间桶数=%s, 总请求数=%s",
            len(bucket_stats),
            total_requests,
        )

    # 从1小时缓存的时间趋势数据中聚合（只聚合更新范围内的数据）
    hourly_trend = cached_1hr.get("hourly_trend", {})
    trend_hours = hourly_trend.get("hours", [])
    trend_counts = hourly_trend.get("counts", [])

    # 过滤时间范围内的数据并按天聚合
    daily_buckets: Dict[str, int] = defaultdict(int)
    for i, hour_label in enumerate(trend_hours):
        try:
            # 1小时粒度：YYYY-MM-DD HH:00
            bucket_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:00")
            if start_time <= bucket_dt <= end_time:
                day_key = bucket_dt.strftime("%Y-%m-%d")
                count = trend_counts[i] if i < len(trend_counts) else 0
                daily_buckets[day_key] += count
                total_requests += count
        except Exception:
            continue

    # 合并新聚合的天数据到bucket_stats
    for day_key, count in daily_buckets.items():
        bucket_stats[day_key] = count  # 覆盖更新范围内的数据

    # 从1小时缓存的top数据中聚合
    top_ips_1hr = cached_1hr.get("top_ips", [])
    top_paths_1hr = cached_1hr.get("top_paths", [])
    status_dist_1hr = cached_1hr.get("status_distribution", {})
    method_dist_1hr = cached_1hr.get("method_distribution", {})
    attacks_1hr = cached_1hr.get("attacks", [])

    # 聚合IP统计
    for ip_item in top_ips_1hr:
        ip_stats[ip_item["ip"]] += ip_item["count"]

    # 聚合路径统计
    for path_item in top_paths_1hr:
        path_stats[path_item["path"]] += path_item["count"]

    # 聚合状态码统计
    for status_str, count in status_dist_1hr.items():
        status_stats[int(status_str)] += count

    # 聚合方法统计
    for method, count in method_dist_1hr.items():
        method_stats[method] += count

    # 聚合攻击记录
    attack_count = cached_1hr.get("summary", {}).get("attack_count", 0)
    attack_details = attacks_1hr[:50]  # 最多保留50条

    # 计算汇总统计
    error_requests = sum(
        count for status, count in status_stats.items() if status >= 400
    )
    success_requests = sum(
        count for status, count in status_stats.items() if 200 <= status < 300
    )
    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

    # 获取top数据
    top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]
    top_paths = sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 按时间排序
    sorted_buckets = sorted(bucket_stats.items())
    bucket_labels = [item[0] for item in sorted_buckets]
    bucket_counts = [item[1] for item in sorted_buckets]

    # 获取错误日志统计（从1小时缓存中获取）
    error_log_count = cached_1hr.get("summary", {}).get("error_log_count", 0)

    result = {
        "success": True,
        "time_range_hours": time_range_hours,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "analysis_status": "success",
        "analysis_status_message": None,
        "is_analyzing": False,  # 分析完成时，is_analyzing 应该为 False
        "last_analysis_time": cached_1hr.get("last_analysis_time"),
        "analyzed_lines": total_requests,
        "summary": {
            "total_requests": total_requests,
            "success_requests": success_requests,
            "error_requests": error_requests,
            "error_rate": round(error_rate, 2),
            "attack_count": attack_count,
            "error_log_count": error_log_count,
        },
        "status_distribution": {str(k): v for k, v in status_stats.items()},
        "method_distribution": dict(method_stats),
        "top_ips": [{"ip": ip, "count": count} for ip, count in top_ips],
        "top_paths": [{"path": path, "count": count} for path, count in top_paths],
        "hourly_trend": {
            "hours": bucket_labels,
            "counts": bucket_counts,
        },
        "attacks": attack_details,
    }

    logger.info(
        "[statistics] 从1小时缓存聚合完成：time_range_hours=%s, total_requests=%s, 时间桶数=%s",
        time_range_hours,
        total_requests,
        len(bucket_labels),
    )

    return result


def reset_analysis_state() -> None:
    """
    重置全局分析任务状态。
    在程序启动时应调用一次，避免沿用上一次进程中的"分析中"等状态。
    """
    _state_manager.reset()

    # 清理所有任务组
    with _task_groups_lock:
        _task_groups.clear()
        logger.info("[statistics] 已清理所有任务组")

    logger.info("[statistics] 分析任务状态已重置")


# 程序启动时重置分析状态
reset_analysis_state()


def _run_analyze_in_background(
    time_range_hours: int = 24,
    is_5min: bool = False,
    trigger: str = "manual",
    full: bool = False,
    task_group_id: Optional[str] = None,
) -> None:
    """
    在单独线程中运行日志分析，避免阻塞请求线程

    Args:
        task_group_id: 任务组ID，用于统一管理多个子任务。如果为None，则作为独立任务
    """

    def _task():
        try:
            analyze_logs(
                time_range_hours=time_range_hours,
                is_5min=is_5min,
                use_cache=False,
                trigger=trigger,
                full=full,
                task_group_id=task_group_id,
            )
        except Exception as e:
            # 如果是任务组的一部分，需要通知任务组
            if task_group_id:
                _notify_task_group_complete(task_group_id, success=False, error=str(e))
            else:
                # 独立任务：确保异常时也重置运行状态
                _state_manager.finish_task(success=False, error=str(e))
            logger.exception(
                "[statistics] 后台分析任务异常，time_range_hours=%s, error=%s",
                time_range_hours,
                e,
            )

    # 如果是独立任务且已经在分析中，直接跳过
    if not task_group_id and _state_manager.is_running:
        logger.info(
            "[statistics] 后台分析已在进行中，本次触发将被忽略（hours=%s）",
            time_range_hours,
        )
        return

    t = threading.Thread(target=_task, daemon=True)
    t.start()


def analyze_logs(
    time_range_hours: int = 24,
    is_5min: bool = False,  # 是否为5分钟分析
    use_cache: bool = True,
    trigger: str = "auto",
    save_cache: bool = True,
    full: bool = False,  # 是否全量分析
    task_group_id: Optional[str] = None,  # 任务组ID，用于统一管理多个子任务
) -> Dict:
    """
    分析日志并返回完整统计数据（保留用于兼容性）

    Args:
        time_range_hours: 时间范围（小时，整数：1, 24等），当 is_5min=True 时此参数无效
        is_5min: 是否为5分钟分析（True=5分钟，False=使用time_range_hours）
        use_cache: 是否使用缓存
        trigger: 触发方式（auto / manual / watcher / auto_fallback）
        save_cache: 是否保存到缓存
        full: 是否全量分析（True=分析整个日志文件，False=只分析指定时间范围内的日志）
    """
    logger.info(
        "[statistics] 开始分析访问日志，is_5min=%s, time_range_hours=%s, use_cache=%s, trigger=%s, full=%s",
        is_5min,
        time_range_hours if not is_5min else "N/A",
        use_cache,
        trigger,
        full,
    )

    # 尝试从缓存获取
    if use_cache:
        if is_5min:
            cached_data = get_cached_statistics_5min(max_age_minutes=5)
        else:
            cached_data = get_cached_statistics(
                int(time_range_hours), max_age_minutes=5
            )
        if cached_data:
            logger.info(
                "[statistics] 命中统计缓存，直接返回结果，time_range_hours=%s",
                time_range_hours,
            )
            return cached_data

    # 如果不是5分钟分析，尝试从缓存聚合
    if not is_5min:
        if time_range_hours == 1:
            # 1小时分析：从5分钟缓存聚合
            # 如果是增量分析，只更新最近1小时的数据
            # 如果是全量分析，更新整个1小时范围
            if not full:
                # 增量分析：只更新最近1小时的数据
                # 获取5分钟分析的时间范围，只更新该范围
                cached_5min = get_cached_statistics_5min(max_age_minutes=None)
                if cached_5min:
                    # 使用5分钟分析的开始时间作为更新起点
                    update_start = datetime.fromisoformat(
                        cached_5min.get("start_time", "").replace("Z", "+00:00")
                    )
                    if update_start.tzinfo:
                        update_start = update_start.replace(tzinfo=None)
                    logger.info(
                        "[statistics] 1小时增量分析：从5分钟缓存数据聚合，更新范围=%s 到 %s",
                        update_start.isoformat(),
                        datetime.now().isoformat(),
                    )
                    aggregated_result = _aggregate_from_5min_cache(
                        time_range_hours=1,
                        end_time=datetime.now(),
                        update_start_time=update_start,
                    )
                else:
                    aggregated_result = _aggregate_from_5min_cache(
                        time_range_hours=1, end_time=datetime.now()
                    )
            else:
                # 全量分析：更新整个1小时范围
                logger.info(
                    "[statistics] 1小时全量分析：从5分钟缓存数据聚合，不读取日志文件"
                )
                aggregated_result = _aggregate_from_5min_cache(
                    time_range_hours=1, end_time=datetime.now()
                )
            if aggregated_result and save_cache:
                # 保存聚合结果到缓存
                try:
                    save_statistics_cache(
                        time_range_hours=1,
                        data=aggregated_result,
                        start_time=datetime.fromisoformat(
                            aggregated_result["start_time"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                        end_time=datetime.fromisoformat(
                            aggregated_result["end_time"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                    )
                    logger.info("[statistics] 1小时聚合结果已保存到缓存")
                except Exception as e:
                    logger.warning("[statistics] 保存1小时聚合结果失败: %s", e)
            if aggregated_result:
                # 如果是独立任务（非任务组），需要更新状态
                if not task_group_id:
                    summary = aggregated_result.get("summary", {})
                    analyzed_lines = summary.get("total_requests", 0)
                    _state_manager.finish_task(
                        success=True, analyzed_lines=analyzed_lines
                    )
                    logger.debug(
                        "[statistics] 独立任务（聚合完成），time_range_hours=%s, total_requests=%s, is_running=%s",
                        time_range_hours,
                        analyzed_lines,
                        _state_manager.is_running,
                    )
                else:
                    # 通知任务组完成（如果是任务组的一部分）
                    _notify_task_group_complete(task_group_id, success=True)
                return aggregated_result
            else:
                logger.warning("[statistics] 无法从5分钟缓存聚合，将尝试读取日志文件")
                # 注意：这里不返回，继续执行后续的日志文件读取逻辑
        elif time_range_hours == 24:
            # 1天分析：从1小时缓存聚合（如果不存在则从5分钟缓存聚合）
            # 如果是增量分析，只更新最近1天的数据
            # 如果是全量分析，更新整个1天范围
            if not full:
                # 增量分析：只更新最近1天的数据
                # 获取1小时分析的时间范围，只更新该范围
                cached_1hr = get_cached_statistics(1, max_age_minutes=None)
                if cached_1hr:
                    # 使用1小时分析的开始时间作为更新起点
                    update_start = datetime.fromisoformat(
                        cached_1hr.get("start_time", "").replace("Z", "+00:00")
                    )
                    if update_start.tzinfo:
                        update_start = update_start.replace(tzinfo=None)
                    logger.info(
                        "[statistics] 1天增量分析：从1小时缓存数据聚合，更新范围=%s 到 %s",
                        update_start.isoformat(),
                        datetime.now().isoformat(),
                    )
                    aggregated_result = _aggregate_from_1hour_cache(
                        time_range_hours=24,
                        end_time=datetime.now(),
                        update_start_time=update_start,
                    )
                else:
                    aggregated_result = _aggregate_from_1hour_cache(
                        time_range_hours=24, end_time=datetime.now()
                    )
            else:
                # 全量分析：更新整个1天范围
                logger.info(
                    "[statistics] 1天全量分析：从1小时缓存数据聚合，不读取日志文件"
                )
                aggregated_result = _aggregate_from_1hour_cache(
                    time_range_hours=24, end_time=datetime.now()
                )
            if aggregated_result and save_cache:
                # 保存聚合结果到缓存
                try:
                    save_statistics_cache(
                        time_range_hours=24,
                        data=aggregated_result,
                        start_time=datetime.fromisoformat(
                            aggregated_result["start_time"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                        end_time=datetime.fromisoformat(
                            aggregated_result["end_time"].replace("Z", "+00:00")
                        ).replace(tzinfo=None),
                    )
                    logger.info("[statistics] 1天聚合结果已保存到缓存")
                except Exception as e:
                    logger.warning("[statistics] 保存1天聚合结果失败: %s", e)
            if aggregated_result:
                # 如果是独立任务（非任务组），需要更新状态
                if not task_group_id:
                    summary = aggregated_result.get("summary", {})
                    analyzed_lines = summary.get("total_requests", 0)
                    _state_manager.finish_task(
                        success=True, analyzed_lines=analyzed_lines
                    )
                    logger.debug(
                        "[statistics] 独立任务（聚合完成），time_range_hours=%s, total_requests=%s, is_running=%s",
                        time_range_hours,
                        analyzed_lines,
                        _state_manager.is_running,
                    )
                else:
                    # 通知任务组完成（如果是任务组的一部分）
                    _notify_task_group_complete(task_group_id, success=True)
                return aggregated_result
            else:
                logger.warning("[statistics] 无法从缓存聚合，将尝试读取日志文件")
                # 注意：这里不返回，继续执行后续的日志文件读取逻辑

    access_log_path = _resolve_access_log_path()
    error_log_path = _resolve_error_log_path()

    # 读取同时间范围下的历史缓存，用于增量分析的锚点
    if is_5min:
        previous_cache = get_cached_statistics_5min(max_age_minutes=None)
        # 5分钟分析：使用5分钟的时间范围
        actual_time_range_hours = 5 / 60  # 用于时间范围计算
    else:
        previous_cache = get_cached_statistics(
            int(time_range_hours), max_age_minutes=None
        )
        actual_time_range_hours = int(time_range_hours)

    previous_last_analysis_time_str: Optional[str] = None
    previous_last_analysis_time: Optional[datetime] = None
    if previous_cache:
        previous_last_analysis_time_str = previous_cache.get("last_analysis_time")
        if previous_last_analysis_time_str:
            try:
                # 解析历史分析时间（可能是 ISO 格式字符串）
                previous_last_analysis_time = datetime.fromisoformat(
                    previous_last_analysis_time_str.replace("Z", "+00:00")
                )
                # 转换为本地时间（如果有时区信息）
                if previous_last_analysis_time.tzinfo:
                    previous_last_analysis_time = previous_last_analysis_time.replace(
                        tzinfo=None
                    )
            except Exception:
                previous_last_analysis_time = None

    # 计算时间范围
    end_time = datetime.now()

    # 增量分析：使用"上次分析时间"作为锚点，只读取该时间点之后的日志
    # 全量分析：按照时间段进行分析，而不是分析整个日志文件
    # - 5分钟分析：分析最近1小时的数据
    # - 1小时分析：分析最近1天的数据
    # - 1天分析：分析最近7天的数据
    if full:
        # 全量分析：统一分析最近7天的数据（超过7天的数据不再处理）
        start_time = end_time - timedelta(days=7)
        if is_5min:
            logger.info(
                "[statistics] 全量分析模式（5分钟）：将分析最近7天的数据（%s 到 %s）",
                start_time.isoformat(),
                end_time.isoformat(),
            )
        elif time_range_hours <= 1:
            logger.info(
                "[statistics] 全量分析模式（1小时）：将分析最近7天的数据（%s 到 %s）",
                start_time.isoformat(),
                end_time.isoformat(),
            )
        else:
            logger.info(
                "[statistics] 全量分析模式（1天）：将分析最近7天的数据（%s 到 %s）",
                start_time.isoformat(),
                end_time.isoformat(),
            )
    elif previous_last_analysis_time:
        # 增量分析：使用上次分析时间作为起点
        # 为了确保不遗漏最近几分钟的数据，我们使用一个更早的时间点作为起点
        # 这样可以处理时间戳不准确或系统时间变化的情况
        start_time = previous_last_analysis_time - timedelta(
            minutes=5
        )  # 往前推5分钟，确保不遗漏
        logger.info(
            "[statistics] 增量分析模式：从上次分析时间 %s 往前推5分钟（%s）开始读取（锚点模式，容错处理）",
            previous_last_analysis_time.isoformat(),
            start_time.isoformat(),
        )
    else:
        # 首次分析或没有历史锚点：使用时间范围
        # 对于增量分析，应该读取最近 actual_time_range_hours 小时的数据
        # 但为了确保不遗漏最近几分钟的数据，我们使用一个更宽松的时间范围
        # 对于5分钟分析，读取最近10分钟的数据；对于1小时分析，读取最近2小时的数据；对于24小时分析，读取最近25小时的数据
        if is_5min:
            # 5分钟分析：读取最近10分钟的数据，确保不遗漏
            buffer_hours = 10 / 60
        elif time_range_hours <= 1:
            # 1小时分析：读取最近2小时的数据
            buffer_hours = 2
        else:
            # 24小时分析：读取最近25小时的数据
            buffer_hours = time_range_hours + 1
        start_time = end_time - timedelta(hours=buffer_hours)
        logger.info(
            "[statistics] 首次分析模式：使用时间范围 %s 到 %s（缓冲时间范围：%s 小时）",
            start_time.isoformat(),
            end_time.isoformat(),
            buffer_hours,
        )

    # 标记分析开始（任务级状态）
    # 如果是任务组的一部分，不更新全局状态（由任务组统一管理）
    # 如果是独立任务，更新全局状态
    if not task_group_id:
        _state_manager.start_task(trigger=trigger)
        logger.debug(
            "[statistics] 独立分析任务开始，当前任务数=%s, time_range_hours=%s",
            _state_manager.task_counter,
            time_range_hours,
        )
    else:
        # 任务组任务：只在第一次启动时设置开始时间（已在触发时设置）
        logger.debug(
            "[statistics] 任务组子任务开始，task_group_id=%s, time_range_hours=%s",
            task_group_id[:8] if task_group_id else "None",
            time_range_hours,
        )

    access_log_file = Path(access_log_path)

    # 先从尾部读取并解析出目标时间范围内的日志条目列表
    # 然后使用多线程对条目列表做并行统计，加快大数据量下的分析速度
    entries: List[Dict[str, Any]] = []
    # 上次分析时间：按“日志中最后一条有效记录的时间”来定义
    last_entry_time: Optional[datetime] = None

    start_ts = datetime.now()

    # 统一使用分批处理（全量和增量分析共用）
    # 全量分析：大批次（100000条）避免内存问题
    # 增量分析：小批次（1000条）或直接处理，确保及时保存
    BATCH_SIZE = 100000 if full else 1000  # 全量用大批次，增量用小批次
    batch_entries: List[Dict[str, Any]] = []
    total_parsed = 0  # 实际读取并解析的日志行数（可能包含时间范围外的）
    in_range_count = 0  # 时间范围内的日志行数

    # 初始化全局统计结果（全量和增量分析共用）
    ip_stats: Dict[str, int] = defaultdict(int)
    status_stats: Dict[int, int] = defaultdict(int)
    path_stats: Dict[str, int] = defaultdict(int)
    method_stats: Dict[str, int] = defaultdict(int)
    bucket_stats: Dict[str, int] = defaultdict(int)
    attack_count = 0
    attack_details: List[Dict[str, Any]] = []

    # 按小时分组统计数据，每处理完一小时就保存一次（全量和增量分析共用）
    current_hour_start: Optional[datetime] = None
    current_hour_end: Optional[datetime] = None
    current_hour_parsed = 0

    def _aggregate_entries(entries_batch: List[Dict[str, Any]]) -> tuple:
        """
        统一处理一批条目并返回统计结果（全量和增量分析共用）

        Returns:
            (ip_stats, status_stats, path_stats, method_stats, bucket_stats, attack_count, attack_details)
        """
        local_ip: Dict[str, int] = defaultdict(int)
        local_status: Dict[int, int] = defaultdict(int)
        local_path: Dict[str, int] = defaultdict(int)
        local_method: Dict[str, int] = defaultdict(int)
        local_bucket: Dict[str, int] = defaultdict(int)
        local_attack_count = 0
        local_attacks: List[Dict[str, Any]] = []

        for entry in entries_batch:
            # 统计IP访问
            local_ip[entry["ip"]] += 1

            # 统计状态码
            status = entry["status"]
            local_status[status] += 1

            # 统计路径
            local_path[entry["path"]] += 1

            # 统计HTTP方法
            local_method[entry["method"]] += 1

            # 按时间桶统计
            dt = entry.get("date")
            if not dt:
                # 如果没有日期，跳过时间桶统计
                logger.warning("[statistics] 日志条目缺少日期字段: %s", entry)
                continue

            if is_5min:  # 5分钟数据
                # 5 分钟对齐：00,05,10,...,55
                rounded_minute = (dt.minute // 5) * 5
                bucket_dt = dt.replace(minute=rounded_minute, second=0, microsecond=0)
                bucket_key = bucket_dt.strftime("%Y-%m-%d %H:%M")
            elif time_range_hours >= 24:  # 1天及以上
                # 按天聚合
                bucket_key = dt.strftime("%Y-%m-%d")
            else:
                # 按小时聚合（1小时到1天之间）
                bucket_key = dt.strftime("%Y-%m-%d %H:00")

            local_bucket[bucket_key] += 1

            # 调试：记录前几个时间桶
            if len(local_bucket) <= 3:
                logger.debug(
                    "[statistics] 时间桶统计示例：bucket_key=%s, count=%s, dt=%s",
                    bucket_key,
                    local_bucket[bucket_key],
                    dt.isoformat(),
                )

            # 检测攻击
            attacks = detect_attack(entry)
            if attacks:
                local_attack_count += 1
                local_attacks.append(
                    {
                        "time": entry["date"].isoformat(),
                        "ip": entry["ip"],
                        "path": entry["path"],
                        "status": status,
                        "attacks": attacks,
                    }
                )

        return (
            local_ip,
            local_status,
            local_path,
            local_method,
            local_bucket,
            local_attack_count,
            local_attacks,
        )

    try:
        # 全量分析：不使用 pygtail，直接从文件尾部读取整个文件（从新到旧）
        # 增量分析：使用 pygtail 进行增量读取（从旧到新）
        # 传递正确的 full 参数，让 iter_log_lines_from_tail 选择正确的读取模式
        for line in iter_log_lines_from_tail(
            access_log_file,
            use_pygtail=not full,  # 全量时不使用pygtail
            full=full,  # 传递正确的full参数
        ):
            entry = parse_access_log_line(line.strip())
            if not entry or not entry.get("date"):
                continue

            # 全量分析：按照时间段过滤，只读取指定时间范围内的日志
            # 增量分析（使用 pygtail）：pygtail 已经只读取了新增内容，但仍需要时间过滤
            #       因为 pygtail 是基于文件位置的，而我们需要基于时间戳的锚点
            if start_time:
                entry_time = entry["date"]
                current_time = datetime.now()

                # 如果日志时间戳在未来（超过当前时间1小时），可能是系统时间问题，跳过这条日志
                if entry_time > current_time + timedelta(hours=1):
                    logger.warning(
                        "[statistics] 检测到未来时间戳的日志：%s（当前时间：%s），跳过",
                        entry_time.isoformat(),
                        current_time.isoformat(),
                    )
                    continue

                # 时间过滤逻辑
                if full:
                    # 全量分析：只处理时间范围内的日志（start_time <= entry_time <= end_time）
                    # 日志从新到旧读取，跳过时间范围外的日志
                    if entry_time < start_time or entry_time > end_time:
                        continue
                else:
                    # 增量分析：使用 pygtail 读取新内容（从旧到新）
                    # 只处理时间戳大于等于 start_time 的日志，跳过早于 start_time 的日志
                    # 因为 pygtail 已经只读取了新内容，所以不需要停止读取
                    if entry_time < start_time:
                        # 跳过早于 start_time 的日志（可能是容错时间范围内的旧日志）
                        continue

            # 记录最新的日志时间（用于"上次分析时间"展示）
            # 增量分析时，日志从旧到新读取（pygtail），所以最后一条就是最新的
            # 全量分析时，日志从新到旧读取，需要比较找到最新的
            if full:
                # 全量分析：从新到旧读取，需要比较找到最新的
                if (last_entry_time is None) or (entry["date"] > last_entry_time):
                    last_entry_time = entry["date"]
            else:
                # 增量分析：从旧到新读取，最后一条就是最新的
                last_entry_time = entry["date"]

            # 实时更新分析进度（用于任务状态接口）
            # 使用范围内的行数作为 analyzed_lines
            _state_manager.update_progress(last_entry_time, in_range_count)

            # 全量分析时，每5000行输出一次进度（让用户知道任务在运行）
            if full and total_parsed > 0 and total_parsed % 5000 == 0:
                logger.info(
                    "[statistics] 全量分析进度：已读取 %s 行, 范围内 %s 行, 最后日志时间=%s",
                    total_parsed,
                    in_range_count,
                    last_entry_time.isoformat() if last_entry_time else "None",
                )

            # 调试：记录前几条日志的时间戳（全量分析时）
            elif full and total_parsed < 3:
                logger.debug(
                    "[statistics] 全量分析：第 %s 条日志，时间=%s, 范围=[%s, %s]",
                    total_parsed + 1,
                    entry["date"].isoformat(),
                    start_time.isoformat() if start_time else "None",
                    end_time.isoformat(),
                )

            # 统一处理：全量和增量分析都使用批次处理
            batch_entries.append(entry)
            total_parsed += 1
            in_range_count += 1  # 能到这里说明已经通过了时间过滤，在范围内

            # 检查是否需要按小时保存（每处理一条日志都检查）
            if save_cache and entry.get("date"):
                entry_hour = entry["date"].replace(minute=0, second=0, microsecond=0)

                # 如果当前小时与上次保存的小时不同，保存上一小时的数据
                if current_hour_start is not None and entry_hour != current_hour_start:
                    # 先处理当前批次，确保统计数据是最新的
                    if batch_entries:
                        (
                            local_ip,
                            local_status,
                            local_path,
                            local_method,
                            local_bucket,
                            local_attack_count,
                            local_attacks,
                        ) = _aggregate_entries(batch_entries)

                        # 合并统计结果
                        for k, v in local_ip.items():
                            ip_stats[k] += v
                        for k, v in local_status.items():
                            status_stats[k] += v
                        for k, v in local_path.items():
                            path_stats[k] += v
                        for k, v in local_method.items():
                            method_stats[k] += v
                        for k, v in local_bucket.items():
                            bucket_stats[k] += v
                        attack_count += local_attack_count
                        attack_details.extend(local_attacks)
                        batch_entries = []  # 清空批次

                    # 保存上一小时的数据（全量和增量分析共用逻辑）
                    try:
                        # 计算上一小时的统计结果
                        hour_total = sum(status_stats.values())
                        hour_error = sum(
                            count
                            for status, count in status_stats.items()
                            if status >= 400
                        )
                        hour_success = sum(
                            count
                            for status, count in status_stats.items()
                            if 200 <= status < 300
                        )
                        hour_error_rate = (
                            (hour_error / hour_total * 100) if hour_total > 0 else 0.0
                        )

                        # 获取当前小时的 top IPs 和 paths
                        hour_top_ips = sorted(
                            ip_stats.items(), key=lambda x: x[1], reverse=True
                        )[:10]
                        hour_top_paths = sorted(
                            path_stats.items(), key=lambda x: x[1], reverse=True
                        )[:10]

                        # 提取当前小时的时间桶数据（用于 hourly_trend）
                        # 注意：对于5分钟分析，应该保存所有时间桶数据，而不是只保存当前小时的
                        hour_bucket_stats = {}
                        for bucket_key, count in bucket_stats.items():
                            try:
                                # 解析时间桶键，判断是否属于当前小时
                                if is_5min:  # 5分钟粒度
                                    bucket_dt = datetime.strptime(
                                        bucket_key, "%Y-%m-%d %H:%M"
                                    )
                                    # 对于5分钟分析，保存所有时间桶（不限制在当前小时）
                                    # 因为5分钟分析需要展示整个时间范围的趋势
                                    hour_bucket_stats[bucket_key] = count
                                elif time_range_hours >= 24:  # 按天
                                    bucket_dt = datetime.strptime(
                                        bucket_key, "%Y-%m-%d"
                                    )
                                    # 判断是否属于当前小时（对于按天的情况，判断是否属于当天）
                                    bucket_hour = bucket_dt.replace(
                                        hour=0, minute=0, second=0, microsecond=0
                                    )
                                    if bucket_hour == current_hour_start.replace(
                                        hour=0, minute=0, second=0, microsecond=0
                                    ):
                                        hour_bucket_stats[bucket_key] = count
                                else:  # 按小时
                                    bucket_dt = datetime.strptime(
                                        bucket_key, "%Y-%m-%d %H:00"
                                    )
                                    # 判断是否属于当前小时
                                    bucket_hour = bucket_dt.replace(
                                        minute=0, second=0, microsecond=0
                                    )
                                    if bucket_hour == current_hour_start:
                                        hour_bucket_stats[bucket_key] = count
                            except Exception:
                                # 解析失败，跳过
                                continue

                        # 按时间排序统计数据
                        sorted_buckets = sorted(hour_bucket_stats.items())
                        bucket_labels = [item[0] for item in sorted_buckets]
                        bucket_counts = [item[1] for item in sorted_buckets]

                        # 增量分析：合并历史数据（包括时间桶数据）
                        if not full:
                            if is_5min:
                                previous_hour_cache = get_cached_statistics_5min(
                                    max_age_minutes=None
                                )
                            else:
                                previous_hour_cache = get_cached_statistics(
                                    int(time_range_hours), max_age_minutes=None
                                )
                            if previous_hour_cache:
                                # 合并历史数据
                                prev_summary = previous_hour_cache.get("summary", {})
                                hour_total += prev_summary.get("total_requests", 0)
                                attack_count += prev_summary.get("attack_count", 0)

                                # 合并 IP、状态码、路径、方法统计
                                prev_ip_stats = previous_hour_cache.get("top_ips", [])
                                for ip_item in prev_ip_stats:
                                    ip_stats[ip_item["ip"]] += ip_item["count"]

                                prev_status_stats = previous_hour_cache.get(
                                    "status_distribution", {}
                                )
                                for status, count in prev_status_stats.items():
                                    status_stats[int(status)] += count

                                prev_path_stats = previous_hour_cache.get(
                                    "top_paths", []
                                )
                                for path_item in prev_path_stats:
                                    path_stats[path_item["path"]] += path_item["count"]

                                prev_method_stats = previous_hour_cache.get(
                                    "method_distribution", {}
                                )
                                for method, count in prev_method_stats.items():
                                    method_stats[method] += count

                                # 合并攻击记录
                                prev_attacks = previous_hour_cache.get("attacks", [])
                                attack_details = (prev_attacks + attack_details)[:50]

                                # 合并时间桶数据（重要：确保 hourly_trend 包含所有时间桶）
                                prev_trend = previous_hour_cache.get("hourly_trend", {})
                                prev_bucket_labels = prev_trend.get("hours", [])
                                prev_bucket_counts = prev_trend.get("counts", [])
                                prev_bucket_stats = dict(
                                    zip(prev_bucket_labels, prev_bucket_counts)
                                )

                                # 合并时间桶到 hour_bucket_stats
                                for bucket_key, count in prev_bucket_stats.items():
                                    hour_bucket_stats[bucket_key] = (
                                        hour_bucket_stats.get(bucket_key, 0) + count
                                    )

                                # 重新排序
                                sorted_buckets = sorted(hour_bucket_stats.items())
                                bucket_labels = [item[0] for item in sorted_buckets]
                                bucket_counts = [item[1] for item in sorted_buckets]

                                # 重新计算 top IPs 和 paths（基于合并后的数据）
                                hour_top_ips = sorted(
                                    ip_stats.items(), key=lambda x: x[1], reverse=True
                                )[:10]
                                hour_top_paths = sorted(
                                    path_stats.items(),
                                    key=lambda x: x[1],
                                    reverse=True,
                                )[:10]

                                # 重新计算错误率和成功请求数
                                hour_error = sum(
                                    count
                                    for status, count in status_stats.items()
                                    if status >= 400
                                )
                                hour_success = sum(
                                    count
                                    for status, count in status_stats.items()
                                    if 200 <= status < 300
                                )
                                hour_total = sum(status_stats.values())
                                hour_error_rate = (
                                    (hour_error / hour_total * 100)
                                    if hour_total > 0
                                    else 0.0
                                )

                        # 构建上一小时的统计结果
                        hour_result = {
                            "success": True,
                            "time_range_hours": (
                                5 / 60 if is_5min else int(time_range_hours)
                            ),
                            "start_time": current_hour_start.isoformat(),
                            "end_time": (
                                current_hour_end.isoformat()
                                if current_hour_end
                                else current_hour_start.isoformat()
                            ),
                            "analysis_status": "success",
                            "analysis_status_message": None,
                            "is_analyzing": full,  # 全量分析进行中，增量分析已完成
                            "last_analysis_time": (
                                current_hour_end.isoformat()
                                if current_hour_end
                                else current_hour_start.isoformat()
                            ),
                            "analyzed_lines": current_hour_parsed,
                            "summary": {
                                "total_requests": hour_total,
                                "success_requests": hour_success,
                                "error_requests": hour_error,
                                "error_rate": round(hour_error_rate, 2),
                                "attack_count": attack_count,
                                "error_log_count": 0,  # 错误日志统计在最后统一处理
                            },
                            "status_distribution": {
                                str(k): v for k, v in status_stats.items()
                            },
                            "method_distribution": dict(method_stats),
                            "top_ips": [
                                {"ip": ip, "count": count} for ip, count in hour_top_ips
                            ],
                            "top_paths": [
                                {"path": path, "count": count}
                                for path, count in hour_top_paths
                            ],
                            "hourly_trend": {
                                "hours": bucket_labels,
                                "counts": bucket_counts,
                            },
                            "attacks": attack_details[:50],
                        }

                        # 根据 is_5min 选择保存函数
                        if is_5min:
                            save_statistics_cache_5min(
                                data=hour_result,
                                start_time=current_hour_start,
                                end_time=(
                                    current_hour_end
                                    if current_hour_end
                                    else current_hour_start
                                ),
                                last_log_position=0,
                            )
                        else:
                            save_statistics_cache(
                                time_range_hours=int(time_range_hours),
                                data=hour_result,
                                start_time=current_hour_start,
                                end_time=(
                                    current_hour_end
                                    if current_hour_end
                                    else current_hour_start
                                ),
                                last_log_position=0,
                            )
                        logger.info(
                            "[statistics] %s：已保存 %s 小时的数据（%s 条日志）",
                            "全量分析" if full else "增量分析",
                            current_hour_start.strftime("%Y-%m-%d %H:00"),
                            current_hour_parsed,
                        )
                    except Exception as e:
                        logger.warning("[statistics] 保存小时统计数据失败: %s", e)

                    # 重置当前小时的统计（但保留全局统计用于最终合并）
                    current_hour_start = entry_hour
                    current_hour_end = entry["date"]
                    current_hour_parsed = 0
                elif current_hour_start is None:
                    # 初始化第一小时
                    current_hour_start = entry_hour
                    current_hour_end = entry["date"]
                    current_hour_parsed = 0
                else:
                    # 更新当前小时的结束时间和解析行数
                    if entry["date"] > current_hour_end:
                        current_hour_end = entry["date"]
                    current_hour_parsed = total_parsed

            # 当批次满了，立即处理这一批并合并结果（全量和增量分析共用）
            if len(batch_entries) >= BATCH_SIZE:
                (
                    local_ip,
                    local_status,
                    local_path,
                    local_method,
                    local_bucket,
                    local_attack_count,
                    local_attacks,
                ) = _aggregate_entries(batch_entries)

                # 合并统计结果
                for k, v in local_ip.items():
                    ip_stats[k] += v
                for k, v in local_status.items():
                    status_stats[k] += v
                for k, v in local_path.items():
                    path_stats[k] += v
                for k, v in local_method.items():
                    method_stats[k] += v
                for k, v in local_bucket.items():
                    bucket_stats[k] += v
                attack_count += local_attack_count
                attack_details.extend(local_attacks)

                # 清空批次，释放内存
                batch_entries = []
                logger.info(
                    "[statistics] %s进度：已解析并统计 %s 条日志",
                    "全量分析" if full else "增量分析",
                    total_parsed,
                )

        # 处理最后一批（全量和增量分析共用）
        if batch_entries:
            (
                local_ip,
                local_status,
                local_path,
                local_method,
                local_bucket,
                local_attack_count,
                local_attacks,
            ) = _aggregate_entries(batch_entries)

            # 合并统计结果
            for k, v in local_ip.items():
                ip_stats[k] += v
            for k, v in local_status.items():
                status_stats[k] += v
            for k, v in local_path.items():
                path_stats[k] += v
            for k, v in local_method.items():
                method_stats[k] += v
            for k, v in local_bucket.items():
                bucket_stats[k] += v
            attack_count += local_attack_count
            attack_details.extend(local_attacks)

            batch_entries = []  # 清空
            logger.info(
                "[statistics] %s：解析并统计完成，总行数=%s",
                "全量分析" if full else "增量分析",
                total_parsed,
            )

        # 处理最后一批（如果有剩余数据）
        if batch_entries:
            (
                local_ip,
                local_status,
                local_path,
                local_method,
                local_bucket,
                local_attack_count,
                local_attacks,
            ) = _aggregate_entries(batch_entries)

            # 合并统计结果
            for k, v in local_ip.items():
                ip_stats[k] += v
            for k, v in local_status.items():
                status_stats[k] += v
            for k, v in local_path.items():
                path_stats[k] += v
            for k, v in local_method.items():
                method_stats[k] += v
            for k, v in local_bucket.items():
                bucket_stats[k] += v
            attack_count += local_attack_count
            attack_details.extend(local_attacks)
            batch_entries = []  # 清空

        # 保存最后一小时的数据（全量和增量分析共用）
        if save_cache and current_hour_start is not None:
            try:
                # 计算最后一小时的统计结果
                hour_total = sum(status_stats.values())
                hour_error = sum(
                    count for status, count in status_stats.items() if status >= 400
                )
                hour_success = sum(
                    count
                    for status, count in status_stats.items()
                    if 200 <= status < 300
                )
                hour_error_rate = (
                    (hour_error / hour_total * 100) if hour_total > 0 else 0.0
                )

                # 获取最后一小时的 top IPs 和 paths
                hour_top_ips = sorted(
                    ip_stats.items(), key=lambda x: x[1], reverse=True
                )[:10]
                hour_top_paths = sorted(
                    path_stats.items(), key=lambda x: x[1], reverse=True
                )[:10]

                # 提取最后一小时的时间桶数据（用于 hourly_trend）
                hour_bucket_stats = {}
                for bucket_key, count in bucket_stats.items():
                    try:
                        # 解析时间桶键，判断是否属于当前小时
                        if is_5min:  # 5分钟粒度
                            bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d %H:%M")
                        elif time_range_hours >= 24:  # 按天
                            bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d")
                        else:  # 按小时
                            bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d %H:00")

                        # 判断是否属于当前小时
                        bucket_hour = bucket_dt.replace(
                            minute=0, second=0, microsecond=0
                        )
                        if bucket_hour == current_hour_start:
                            hour_bucket_stats[bucket_key] = count
                    except Exception:
                        # 解析失败，跳过
                        continue

                # 按时间排序统计数据
                sorted_buckets = sorted(hour_bucket_stats.items())
                bucket_labels = [item[0] for item in sorted_buckets]
                bucket_counts = [item[1] for item in sorted_buckets]

                # 构建最后一小时的统计结果
                hour_result = {
                    "success": True,
                    "time_range_hours": 5 / 60 if is_5min else int(time_range_hours),
                    "start_time": current_hour_start.isoformat(),
                    "end_time": (
                        current_hour_end.isoformat()
                        if current_hour_end
                        else current_hour_start.isoformat()
                    ),
                    "analysis_status": "success",
                    "analysis_status_message": None,
                    "is_analyzing": False,  # 全量分析完成
                    "last_analysis_time": (
                        current_hour_end.isoformat()
                        if current_hour_end
                        else current_hour_start.isoformat()
                    ),
                    "analyzed_lines": current_hour_parsed,
                    "summary": {
                        "total_requests": hour_total,
                        "success_requests": hour_success,
                        "error_requests": hour_error,
                        "error_rate": round(hour_error_rate, 2),
                        "attack_count": attack_count,
                        "error_log_count": 0,
                    },
                    "status_distribution": dict(status_stats),
                    "method_distribution": dict(method_stats),
                    "top_ips": [
                        {"ip": ip, "count": count} for ip, count in hour_top_ips
                    ],
                    "top_paths": [
                        {"path": path, "count": count} for path, count in hour_top_paths
                    ],
                    "hourly_trend": {
                        "hours": bucket_labels,
                        "counts": bucket_counts,
                    },
                    "attacks": attack_details[:50],
                }

                # 根据 is_5min 选择保存函数
                if is_5min:
                    save_statistics_cache_5min(
                        data=hour_result,
                        start_time=current_hour_start,
                        end_time=(
                            current_hour_end if current_hour_end else current_hour_start
                        ),
                        last_log_position=0,
                    )
                else:
                    save_statistics_cache(
                        time_range_hours=int(time_range_hours),
                        data=hour_result,
                        start_time=current_hour_start,
                        end_time=(
                            current_hour_end if current_hour_end else current_hour_start
                        ),
                        last_log_position=0,
                    )
                logger.info(
                    "[statistics] 全量分析：已保存最后一小时 %s 的数据（%s 条日志）",
                    current_hour_start.strftime("%Y-%m-%d %H:00"),
                    current_hour_parsed,
                )
            except Exception as e:
                logger.warning("[statistics] 保存最后一小时统计数据失败: %s", e)
    except Exception as e:
        # 确保异常时也重置运行状态
        if task_group_id:
            _notify_task_group_complete(task_group_id, success=False, error=str(e))
        else:
            _state_manager.finish_task(success=False, error=str(e))
            logger.debug(
                "[statistics] 独立分析任务异常结束，剩余任务数=%s, time_range_hours=%s",
                _state_manager.task_counter,
                time_range_hours,
            )
        logger.exception(
            "[statistics] 日志预解析失败，time_range_hours=%s, error=%s",
            time_range_hours,
            e,
        )
        raise

    # 并行统计阶段
    # 本次分析的新日志条目数（用于 analyzed_lines，反映本次实际分析的行数）
    # 注意：即使 total_parsed = 0（没有新数据），任务也已经完成，需要更新状态
    # 重要：new_requests_count 保存本次任务实际处理的行数，不会被历史数据累加
    # 使用 in_range_count（范围内的行数）而不是 total_parsed（可能包含范围外的行数）
    new_requests_count = in_range_count  # 本次任务实际处理的日志行数（范围内）
    total_requests = in_range_count  # 当前统计的请求总数（可能会在合并历史数据时累加）

    if full:
        # 全量分析时，统计结果已经在循环中处理完了，不需要重新统计
        # ip_stats, status_stats 等已经在循环中填充
        pass
    else:
        # 增量分析：需要对 entries 进行统计
        pass

        # 初始化全局统计结果（全量分析时已经在循环中初始化了）
        if not ip_stats:  # 如果还没有初始化（增量分析时）
            ip_stats = defaultdict(int)
            status_stats = defaultdict(int)
            path_stats = defaultdict(int)
            method_stats = defaultdict(int)
            bucket_stats = defaultdict(int)
            attack_count = 0
            attack_details = []

    # _aggregate_chunk 已合并到 _aggregate_entries，这里使用别名保持兼容
    _aggregate_chunk = _aggregate_entries

    # 如果日志条目较多，开启多线程并行统计
    # 全量分析时，统计结果已经在循环中处理完了，跳过这里的统计
    # 注意：增量分析时，entries 变量未定义，这里应该跳过（因为已经在循环中处理了）
    # 实际上，增量分析时，统计结果已经在循环中处理完了，不需要再次统计
    if False and not full:  # 暂时禁用，因为 entries 变量未定义
        max_workers = min(4, os.cpu_count() or 2)
        if total_requests < 1000:
            # 数据量较小时，用单线程避免额外开销
            chunks = [entries]
        else:
            # 将 entries 均匀切成 N 片，交给线程池处理
            chunk_size = max(1, total_requests // max_workers)
            chunks = [
                entries[i : i + chunk_size]
                for i in range(0, total_requests, chunk_size)
            ]

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for (
                    local_ip,
                    local_status,
                    local_path,
                    local_method,
                    local_bucket,
                    local_attack_count,
                    local_attacks,
                ) in executor.map(_aggregate_chunk, chunks):
                    # 合并局部结果到全局
                    for k, v in local_ip.items():
                        ip_stats[k] += v
                    for k, v in local_status.items():
                        status_stats[k] += v
                    for k, v in local_path.items():
                        path_stats[k] += v
                    for k, v in local_method.items():
                        method_stats[k] += v
                    for k, v in local_bucket.items():
                        bucket_stats[k] += v
                    attack_count += local_attack_count
                    attack_details.extend(local_attacks)

            # 增量分析统计完成后，保存最后一小时的数据
            if save_cache and current_hour_start is not None:
                try:
                    # 统计最后一小时的数据
                    hour_entries = [
                        e
                        for e in entries
                        if e.get("date")
                        and e["date"].replace(minute=0, second=0, microsecond=0)
                        == current_hour_start
                    ]

                    if hour_entries:
                        # 计算最后一小时的统计结果（基于已统计的全局数据）
                        hour_total = sum(status_stats.values())
                        hour_error = sum(
                            count
                            for status, count in status_stats.items()
                            if status >= 400
                        )
                        hour_success = sum(
                            count
                            for status, count in status_stats.items()
                            if 200 <= status < 300
                        )
                        hour_error_rate = (
                            (hour_error / hour_total * 100) if hour_total > 0 else 0.0
                        )

                        # 获取最后一小时的 top IPs 和 paths
                        hour_top_ips = sorted(
                            ip_stats.items(), key=lambda x: x[1], reverse=True
                        )[:10]
                        hour_top_paths = sorted(
                            path_stats.items(), key=lambda x: x[1], reverse=True
                        )[:10]

                        # 按时间排序统计数据
                        sorted_buckets = sorted(bucket_stats.items())
                        bucket_labels = [item[0] for item in sorted_buckets]
                        bucket_counts = [item[1] for item in sorted_buckets]

                        # 构建最后一小时的统计结果
                        hour_result = {
                            "success": True,
                            "time_range_hours": (
                                5 / 60 if is_5min else int(time_range_hours)
                            ),
                            "start_time": current_hour_start.isoformat(),
                            "end_time": (
                                current_hour_end.isoformat()
                                if current_hour_end
                                else current_hour_start.isoformat()
                            ),
                            "analysis_status": "success",
                            "analysis_status_message": None,
                            "is_analyzing": False,  # 增量分析完成
                            "last_analysis_time": (
                                current_hour_end.isoformat()
                                if current_hour_end
                                else current_hour_start.isoformat()
                            ),
                            "analyzed_lines": len(hour_entries),
                            "summary": {
                                "total_requests": hour_total,
                                "success_requests": hour_success,
                                "error_requests": hour_error,
                                "error_rate": round(hour_error_rate, 2),
                                "attack_count": attack_count,
                                "error_log_count": 0,
                            },
                            "status_distribution": {
                                str(k): v for k, v in status_stats.items()
                            },
                            "method_distribution": dict(method_stats),
                            "top_ips": [
                                {"ip": ip, "count": count} for ip, count in hour_top_ips
                            ],
                            "top_paths": [
                                {"path": path, "count": count}
                                for path, count in hour_top_paths
                            ],
                            "hourly_trend": {
                                "hours": bucket_labels,
                                "counts": bucket_counts,
                            },
                            "attacks": attack_details[:50],
                        }

                        # 根据 is_5min 选择保存函数
                        if is_5min:
                            save_statistics_cache_5min(
                                data=hour_result,
                                start_time=current_hour_start,
                                end_time=(
                                    current_hour_end
                                    if current_hour_end
                                    else current_hour_start
                                ),
                                last_log_position=0,
                            )
                        else:
                            save_statistics_cache(
                                time_range_hours=int(time_range_hours),
                                data=hour_result,
                                start_time=current_hour_start,
                                end_time=(
                                    current_hour_end
                                    if current_hour_end
                                    else current_hour_start
                                ),
                                last_log_position=0,
                            )
                        logger.info(
                            "[statistics] 增量分析：已保存最后一小时 %s 的数据（%s 条日志）",
                            current_hour_start.strftime("%Y-%m-%d %H:00"),
                            len(hour_entries),
                        )
                except Exception as e:
                    logger.warning(
                        "[statistics] 增量分析保存最后一小时统计数据失败: %s", e
                    )
        except Exception as e:
            # 确保异常时也重置运行状态
            if task_group_id:
                _notify_task_group_complete(task_group_id, success=False, error=str(e))
            else:
                _state_manager.finish_task(success=False, error=str(e))
                logger.debug(
                    "[statistics] 独立分析任务异常结束，剩余任务数=%s, time_range_hours=%s",
                    _state_manager.task_counter,
                    time_range_hours,
                )
            logger.exception(
                "[statistics] 并行统计阶段失败，time_range_hours=%s, error=%s",
                time_range_hours,
                e,
            )
            raise

    # 计算耗时
    end_ts = datetime.now()
    duration = (end_ts - start_ts).total_seconds()

    logger.info(
        "[statistics] 日志分析完成，time_range_hours=%s, total_requests=%s, 耗时=%.2fs, task_group_id=%s",
        time_range_hours,
        total_requests,
        duration,
        task_group_id[:8] if task_group_id else "None",
    )

    # 标记分析结束与耗时
    # 即使是 0 条数据，任务也已经完成，需要更新状态
    # 如果是任务组的一部分，通知任务组；否则更新全局状态
    if task_group_id:
        logger.debug(
            "[statistics] 通知任务组完成：task_group_id=%s, time_range_hours=%s, total_requests=%s",
            task_group_id[:8],
            time_range_hours,
            total_requests,
        )
        _notify_task_group_complete(task_group_id, success=True)
    else:
        # 统一使用状态管理器更新状态（使用本次任务实际处理的行数）
        _state_manager.finish_task(success=True, analyzed_lines=new_requests_count)
        logger.info(
            "[statistics] 独立分析任务正常结束，剩余任务数=%s, time_range_hours=%s, 耗时=%.2fs, is_running=%s, 本次处理=%s行, 总请求数=%s",
            _state_manager.task_counter,
            time_range_hours,
            duration,
            _state_manager.is_running,
            new_requests_count,
            total_requests,
        )

    # 增量分析：如果有历史缓存，需要合并数据
    if not full and previous_cache and previous_cache.get("summary"):
        logger.info(
            "[statistics] 增量分析：开始合并历史数据（历史条目数=%s，新增条目数=%s）",
            previous_cache.get("analyzed_lines", 0),
            total_requests,
        )

        # 合并 IP 统计
        prev_ip_stats = {
            item["ip"]: item["count"] for item in previous_cache.get("top_ips", [])
        }
        for ip, count in prev_ip_stats.items():
            ip_stats[ip] += count

        # 合并路径统计
        prev_path_stats = {
            item["path"]: item["count"] for item in previous_cache.get("top_paths", [])
        }
        for path, count in prev_path_stats.items():
            path_stats[path] += count

        # 合并状态码统计
        prev_status_stats = previous_cache.get("status_distribution", {})
        for status, count in prev_status_stats.items():
            status_stats[int(status)] += count

        # 合并方法统计
        prev_method_stats = previous_cache.get("method_distribution", {})
        for method, count in prev_method_stats.items():
            method_stats[method] += count

        # 合并攻击记录（保留最近的）
        prev_attacks = previous_cache.get("attacks", [])
        attack_details = (prev_attacks + attack_details)[:50]  # 最多保留50条

        # 合并 summary
        prev_summary = previous_cache.get("summary", {})
        total_requests += prev_summary.get("total_requests", 0)
        attack_count += prev_summary.get("attack_count", 0)

        # 重新计算错误率和成功请求数（基于合并后的状态码统计）
        # 注意：这里使用合并后的 total_requests 和 status_stats
        pass  # 将在后面统一计算

        # 时间趋势需要重新计算（因为时间范围是动态的）
        # 先合并历史的时间桶数据
        prev_trend = previous_cache.get("hourly_trend", {})
        prev_bucket_labels = prev_trend.get("hours", [])
        prev_bucket_counts = prev_trend.get("counts", [])
        prev_bucket_stats = dict(zip(prev_bucket_labels, prev_bucket_counts))

        # 合并时间桶
        for bucket_key, count in prev_bucket_stats.items():
            bucket_stats[bucket_key] += count

        # 全量分析：保留所有时间桶数据，不进行时间范围过滤
        # 增量分析：移除超出时间范围的历史数据（只保留 end_time 之前的 time_range_hours 小时内的数据）
        if not full:
            range_start = end_time - timedelta(hours=actual_time_range_hours)
            filtered_bucket_stats = {}
            for bucket_key, count in bucket_stats.items():
                try:
                    # 解析时间桶键
                    if is_5min:
                        # 5分钟粒度：YYYY-MM-DD HH:MM
                        bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d %H:%M")
                    elif time_range_hours >= 24 * 7:
                        # 按天：YYYY-MM-DD
                        bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d")
                    else:
                        # 按小时：YYYY-MM-DD HH:00
                        bucket_dt = datetime.strptime(bucket_key, "%Y-%m-%d %H:00")

                    # 只保留在时间范围内的数据
                    if bucket_dt >= range_start:
                        filtered_bucket_stats[bucket_key] = count
                except Exception:
                    # 解析失败，保留数据（可能是新格式）
                    filtered_bucket_stats[bucket_key] = count

            bucket_stats = filtered_bucket_stats
            logger.info(
                "[statistics] 增量分析：数据合并完成，总条目数=%s，时间桶数=%s",
                total_requests,
                len(bucket_stats),
            )
        else:
            logger.info(
                "[statistics] 全量分析：数据合并完成，总条目数=%s，时间桶数=%s（保留所有时间范围）",
                total_requests,
                len(bucket_stats),
            )

    # 计算错误率和成功请求数（基于最终的状态码统计）
    error_requests = sum(
        count for status, count in status_stats.items() if status >= 400
    )
    success_requests = sum(
        count for status, count in status_stats.items() if 200 <= status < 300
    )
    error_rate = (error_requests / total_requests * 100) if total_requests > 0 else 0

    # 获取访问量前10的IP
    top_ips = sorted(ip_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 获取访问量前10的路径
    top_paths = sorted(path_stats.items(), key=lambda x: x[1], reverse=True)[:10]

    # 按时间排序统计数据
    sorted_buckets = sorted(bucket_stats.items())
    bucket_labels = [item[0] for item in sorted_buckets]
    bucket_counts = [item[1] for item in sorted_buckets]

    # 调试：记录时间桶数据
    logger.info(
        "[statistics] 最终结果：时间桶数量=%s, 总请求数=%s, is_5min=%s, time_range_hours=%s, bucket_stats大小=%s",
        len(bucket_labels),
        total_requests,
        is_5min,
        time_range_hours if not is_5min else "5min",
        len(bucket_stats),
    )
    if len(bucket_labels) > 0:
        logger.info(
            "[statistics] 时间桶范围：%s 到 %s, 前3个时间桶=%s",
            bucket_labels[0] if bucket_labels else "N/A",
            bucket_labels[-1] if bucket_labels else "N/A",
            bucket_labels[:3] if len(bucket_labels) >= 3 else bucket_labels,
        )
    else:
        logger.warning(
            "[statistics] 警告：bucket_stats为空！总请求数=%s, bucket_stats.keys()=%s",
            total_requests,
            list(bucket_stats.keys())[:10] if bucket_stats else [],
        )

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

    # 增量分析：合并历史错误日志统计
    if not full and previous_cache and previous_cache.get("summary"):
        prev_error_log_count = previous_cache.get("summary", {}).get(
            "error_log_count", 0
        )
        error_log_count += prev_error_log_count

    # 计算状态字段
    # “上次分析时间” = 日志中最后一条被分析记录的时间（如果有），否则回退到分析结束时间
    last_analysis_time = (
        last_entry_time or ANALYSIS_STATE.get("last_end_time") or end_time
    )

    result = {
        "success": True,
        "time_range_hours": (
            5 / 60 if is_5min else int(time_range_hours)
        ),  # 前端兼容：5分钟显示为 5/60
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat(),
        # 分析状态相关字段（数据粒度）
        "analysis_status": "success",
        "analysis_status_message": None,
        "is_analyzing": False,  # 分析完成时，is_analyzing 应该为 False
        "last_analysis_time": (
            last_analysis_time.isoformat() if last_analysis_time else None
        ),
        # 分析任务处理的访问日志条数（本次任务实际处理的行数，不含历史累积）
        "analyzed_lines": new_requests_count,
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

    # 调试：记录保存前的数据
    logger.info(
        "[statistics] 准备保存结果：is_5min=%s, hourly_trend数据点数量=%s, 前3个时间点=%s",
        is_5min,
        len(bucket_labels),
        bucket_labels[:3] if bucket_labels else [],
    )

    # 保存到缓存（与是否从缓存读取解耦：后台/手动任务通常 use_cache=False 但仍需写入缓存）
    if save_cache:
        try:
            # 确保 start_time 不为 None（数据库字段不允许为 NULL）
            # 全量分析时，使用最早的时间桶作为 start_time，如果没有时间桶则使用时间范围起点
            cache_start_time = start_time
            if cache_start_time is None:
                # 全量分析：使用最早的时间桶作为 start_time
                if bucket_stats:
                    # 找到最早的时间桶
                    try:
                        if is_5min:
                            # 5分钟粒度：YYYY-MM-DD HH:MM
                            sorted_buckets = sorted(bucket_stats.keys())
                            earliest_bucket = sorted_buckets[0]
                            cache_start_time = datetime.strptime(
                                earliest_bucket, "%Y-%m-%d %H:%M"
                            )
                        elif time_range_hours >= 24:
                            # 按天：YYYY-MM-DD
                            sorted_buckets = sorted(bucket_stats.keys())
                            earliest_bucket = sorted_buckets[0]
                            cache_start_time = datetime.strptime(
                                earliest_bucket, "%Y-%m-%d"
                            )
                        else:
                            # 按小时：YYYY-MM-DD HH:00
                            sorted_buckets = sorted(bucket_stats.keys())
                            earliest_bucket = sorted_buckets[0]
                            cache_start_time = datetime.strptime(
                                earliest_bucket, "%Y-%m-%d %H:00"
                            )
                        logger.info(
                            "[statistics] 全量分析：使用最早时间桶作为 start_time: %s",
                            cache_start_time.isoformat(),
                        )
                    except Exception as e:
                        logger.warning(
                            "[statistics] 全量分析：解析最早时间桶失败，使用时间范围起点: %s",
                            e,
                        )
                        cache_start_time = end_time - timedelta(
                            hours=actual_time_range_hours
                        )
                else:
                    # 全量分析且没有找到日志时，使用时间范围起点
                    cache_start_time = end_time - timedelta(
                        hours=actual_time_range_hours
                    )
                    logger.debug(
                        "[statistics] 全量分析未找到日志，使用时间范围起点作为 start_time: %s",
                        cache_start_time.isoformat(),
                    )

            # 根据 is_5min 选择保存函数
            if is_5min:
                save_statistics_cache_5min(
                    data=result,
                    start_time=cache_start_time,
                    end_time=end_time,
                    last_log_position=0,
                )
            else:
                save_statistics_cache(
                    time_range_hours=int(time_range_hours),
                    data=result,
                    start_time=cache_start_time,
                    end_time=end_time,
                    last_log_position=0,
                )
        except Exception as e:
            # 缓存失败不影响返回结果
            logger.warning("[statistics] 保存统计缓存失败: %s", e)

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
    - 1小时：从5分钟缓存中获取
    - 1天/7天：从1天缓存中获取
    """
    try:
        # 根据查询时间范围，决定从哪个缓存读取数据
        # 1小时：从5分钟缓存中获取（因为5分钟数据在单独表中）
        # 1天/7天/30天：从1天缓存中获取
        if hours <= 1:
            cached = get_cached_statistics_5min(max_age_minutes=30)
        else:
            cached = get_cached_statistics(24, max_age_minutes=30)

        if cached:
            # 直接返回缓存数据，保持与主分支一致的简单逻辑
            # 时间范围过滤在分析时已经完成，缓存数据就是对应时间范围的数据
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
        # 实时统计：从5分钟缓存中获取（因为5分钟数据在单独表中）
        cached = get_cached_statistics_5min(max_age_minutes=10)
        if cached:
            return cached

        return {
            "success": False,
            "time_range_hours": 1,
            "message": "实时统计数据暂未生成，请稍后重试",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取实时统计数据失败: {str(e)}",
        )


@router.get("/task-status", summary="获取分析任务状态")
async def get_analysis_task_status(
    current_user: User = Depends(get_current_user),
):
    """
    获取分析任务状态（独立接口，不依赖时间范围）

    说明：
    - 返回当前分析任务的实时状态
    - 包括是否在运行、上次分析时间、监听状态等
    - 不依赖缓存数据，直接返回任务状态
    """
    try:
        state = _state_manager.get_state()
        last_start = state.get("last_start_time")
        last_end = state.get("last_end_time")
        is_running = _state_manager.is_running
        last_duration_seconds = state.get("last_duration_seconds") or 0.0
        running_duration_seconds = None
        if is_running and last_start:
            running_duration_seconds = (datetime.now() - last_start).total_seconds()

        # 直接从状态管理器获取任务状态，不依赖缓存
        # 任务状态应该完全通过字段来反馈真实情况
        if is_running:
            # 任务正在运行：使用实时进度
            current_last_entry_time = state.get("current_last_entry_time")
            current_analyzed_lines = state.get("current_analyzed_lines", 0)

            if current_last_entry_time:
                # 有实时进度，使用实时进度
                last_analysis_time = current_last_entry_time
                analyzed_lines = current_analyzed_lines
            else:
                # 任务刚开始，还没有处理任何日志
                last_analysis_time = last_start
                analyzed_lines = 0
        else:
            # 任务未运行：使用最后完成的任务信息
            # last_analysis_time 使用 last_end_time（任务完成时间）
            # analyzed_lines 从状态中获取（任务完成时保存的）
            last_analysis_time = last_end
            analyzed_lines = state.get("last_analyzed_lines", 0)

        # 判断分析状态（直接使用真实的任务状态，不做修正）
        if is_running:
            status = "analyzing"
        elif state.get("last_success") is False:
            status = "failed"
        elif state.get("last_success") is True:
            status = "ready"
        else:
            status = "not_ready"

        return {
            "success": True,
            "status": status,
            "is_running": is_running,
            "last_start_time": last_start.isoformat() if last_start else None,
            "last_end_time": last_end.isoformat() if last_end else None,
            "last_analysis_time": (
                last_analysis_time.isoformat() if last_analysis_time else None
            ),
            "analyzed_lines": analyzed_lines,
            "last_error": state.get("last_error"),
            "last_success": state.get("last_success"),
            "last_trigger": state.get("last_trigger"),
            "last_duration_seconds": last_duration_seconds,
            "running_duration_seconds": running_duration_seconds,
            "watcher_enabled": state.get("watcher_enabled", False),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取任务状态失败: {str(e)}",
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
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间重新解析日志
    - 1小时：从5分钟缓存中获取
    - 1天/7天：从1天缓存中获取
    - 不包含任务状态信息，任务状态请使用 /task-status 接口
    """
    try:
        # 根据查询时间范围，决定从哪个缓存读取数据
        if hours <= 1:
            cached_data = get_cached_statistics_5min(max_age_minutes=None)
        else:
            cached_data = get_cached_statistics(24, max_age_minutes=None)

        if cached_data and cached_data.get("summary"):
            # 计算时间范围
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)

            # 获取上次分析时间：优先使用缓存中的 last_analysis_time，否则使用 end_time
            last_analysis_time_str = cached_data.get(
                "last_analysis_time"
            ) or cached_data.get("end_time")
            # 如果缓存中的时间明显不对（超过1小时），使用当前时间
            if last_analysis_time_str:
                try:
                    last_analysis_dt = datetime.fromisoformat(
                        last_analysis_time_str.replace("Z", "+00:00")
                    )
                    if last_analysis_dt.tzinfo:
                        last_analysis_dt = last_analysis_dt.replace(tzinfo=None)
                    # 如果上次分析时间超过1小时，认为数据过期，使用当前时间
                    if (datetime.now() - last_analysis_dt).total_seconds() > 3600:
                        logger.warning(
                            "[statistics] 缓存中的上次分析时间过旧：%s，使用当前时间",
                            last_analysis_time_str,
                        )
                        last_analysis_time_str = datetime.now().isoformat()
                except Exception:
                    # 解析失败，使用当前时间
                    last_analysis_time_str = datetime.now().isoformat()
            else:
                last_analysis_time_str = datetime.now().isoformat()

            # 获取分析行数：优先使用 analyzed_lines，否则使用 total_requests
            analyzed_lines = cached_data.get("analyzed_lines")
            if analyzed_lines is None or analyzed_lines == 0:
                analyzed_lines = (cached_data.get("summary") or {}).get(
                    "total_requests", 0
                )

            return {
                "success": True,
                "time_range_hours": hours,
                "summary": cached_data.get("summary"),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "last_analysis_time": last_analysis_time_str,
                "analyzed_lines": analyzed_lines,
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


@router.post("/analyze", summary="手动触发统计分析（支持全量/增量）")
async def trigger_statistics_analyze(
    full: bool = Query(
        False,
        description="是否执行全量分析（忽略增量优化，适合日志结构变化或异常后手动重算）",
    ),
    current_user: User = Depends(get_current_user),
):
    """
    手动触发一次统计分析。

    说明：
    - 按时间范围递进分析：5分钟 -> 1小时 -> 1天
    - full=true 时明确表示"全量分析"，优先级最高；
    - 如果当前已有分析任务在运行，则不会重复触发，直接返回提示。
    - 实际分析在后台线程中执行，不阻塞当前请求。
    """
    # 已在分析中，直接返回提示
    if _state_manager.is_running:
        logger.info("[statistics] 手动触发分析被拒绝：当前已有分析任务在进行中")
        return {
            "success": False,
            "message": "统计分析正在进行中，请稍后再试",
            "is_analyzing": True,
        }

    try:
        logger.info(
            "[statistics] 手动触发统计分析开始，full=%s，用户=%s",
            full,
            getattr(current_user, "username", None),
        )

        # 创建任务组，统一管理多个子任务
        # 用户只看到一个分析任务，但后台会并行执行多个时间范围的分析
        # 增量分析时只需要2个任务（1小时和1天聚合），全量分析需要3个任务（5分钟、1小时、1天）
        total_tasks = 3 if full else 2
        task_group_id = _create_task_group(
            total_tasks=total_tasks,
            trigger="manual_full" if full else "manual",
            full=full,
        )

        # 标记任务开始（只设置一次）
        _state_manager.start_task(trigger="manual_full" if full else "manual")

        # 按时间范围递进分析：5分钟 -> 1小时 -> 1天
        # 全量分析：
        #   - 5分钟分析：读取日志文件
        #   - 1小时分析：从5分钟缓存聚合（延迟启动，等待5分钟分析完成）
        #   - 1天分析：从1小时缓存聚合（延迟启动，等待1小时分析完成）
        # 增量分析：
        #   - 跳过5分钟分析（使用现有缓存）
        #   - 1小时分析：直接从5分钟缓存聚合
        #   - 1天分析：从1小时缓存聚合（延迟启动，等待1小时分析完成）
        # 7天的数据从1天的数据中聚合，不需要单独分析

        # 全量分析：先启动5分钟分析（读取日志文件）
        if full:
            _run_analyze_in_background(
                time_range_hours=1,  # 占位符
                is_5min=True,
                trigger="manual_full",
                full=full,
                task_group_id=task_group_id,
            )

        # 延迟启动1小时和1天分析（从缓存聚合）
        def delayed_aggregate_tasks():
            import time
            from app.utils.statistics_cache import (
                get_cached_statistics_5min,
                get_cached_statistics,
            )

            # 定义等待参数（全量和增量分析都需要）
            max_wait_time = 60  # 最多等待60秒
            wait_interval = 2  # 每2秒检查一次

            # 全量分析：等待5分钟分析完成
            # 增量分析：直接开始（使用现有的5分钟缓存）
            if full:
                # 等待5分钟分析完成：轮询检查5分钟缓存是否存在且是最新的
                waited_time = 0
                while waited_time < max_wait_time:
                    cached_5min = get_cached_statistics_5min(max_age_minutes=None)
                    if cached_5min:
                        # 检查缓存是否是最新的（结束时间在最近1分钟内）
                        cache_end_str = cached_5min.get("end_time", "")
                        if cache_end_str:
                            try:
                                cache_end = datetime.fromisoformat(
                                    cache_end_str.replace("Z", "+00:00")
                                )
                                if cache_end.tzinfo:
                                    cache_end = cache_end.replace(tzinfo=None)
                                # 如果缓存结束时间在最近1分钟内，认为5分钟分析已完成
                                if (datetime.now() - cache_end).total_seconds() < 60:
                                    logger.info(
                                        "[statistics] 检测到5分钟分析已完成，开始1小时聚合"
                                    )
                                    break
                            except Exception:
                                pass
                    time.sleep(wait_interval)
                    waited_time += wait_interval
                    logger.debug(
                        "[statistics] 等待5分钟分析完成，已等待 %s 秒", waited_time
                    )
            else:
                # 增量分析：直接使用现有的5分钟缓存，无需等待
                logger.info("[statistics] 增量分析：直接从现有5分钟缓存开始1小时聚合")

            # 启动1小时分析（从5分钟缓存聚合）
            # 注意：1小时和1天任务始终从缓存聚合，所以 full=False
            _run_analyze_in_background(
                time_range_hours=1,
                is_5min=False,
                trigger="manual_full" if full else "manual",
                full=False,  # 从缓存聚合，不读取日志文件
                task_group_id=task_group_id,
            )

            # 等待1小时分析完成：轮询检查1小时缓存是否存在且是最新的
            waited_time = 0
            while waited_time < max_wait_time:
                cached_1hr = get_cached_statistics(1, max_age_minutes=None)
                if cached_1hr:
                    # 检查缓存是否是最新的
                    cache_end_str = cached_1hr.get("end_time", "")
                    if cache_end_str:
                        try:
                            cache_end = datetime.fromisoformat(
                                cache_end_str.replace("Z", "+00:00")
                            )
                            if cache_end.tzinfo:
                                cache_end = cache_end.replace(tzinfo=None)
                            # 如果缓存结束时间在最近1分钟内，认为1小时分析已完成
                            if (datetime.now() - cache_end).total_seconds() < 60:
                                logger.info(
                                    "[statistics] 检测到1小时分析已完成，开始1天聚合"
                                )
                                break
                        except Exception:
                            pass
                time.sleep(wait_interval)
                waited_time += wait_interval
                logger.debug(
                    "[statistics] 等待1小时分析完成，已等待 %s 秒", waited_time
                )

            # 启动1天分析（从1小时缓存聚合）
            # 注意：1天任务始终从缓存聚合，所以 full=False
            _run_analyze_in_background(
                time_range_hours=24,
                is_5min=False,
                trigger="manual_full" if full else "manual",
                full=False,  # 从缓存聚合，不读取日志文件
                task_group_id=task_group_id,
            )

        # 在后台线程中延迟启动聚合任务
        threading.Thread(target=delayed_aggregate_tasks, daemon=True).start()

        return {
            "success": True,
            "message": (
                "全量分析已在后台启动（5分钟 -> 1小时 -> 1天）"
                if full
                else "增量分析已在后台启动（5分钟 -> 1小时 -> 1天）"
            ),
            "is_analyzing": True,
            "full": full,
        }
    except Exception as e:
        logger.exception("[statistics] 手动触发统计分析失败：%s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"触发统计分析失败: {str(e)}",
        )


def _filter_data_by_time_range(
    cached_data: Dict,
    hours: int,
    data_type: str = "all",
) -> Dict:
    """
    根据时间范围过滤缓存数据

    Args:
        cached_data: 缓存数据
        hours: 时间范围（小时）
        data_type: 数据类型（"summary", "top_ips", "top_paths", "status_distribution", "attacks", "all"）

    Returns:
        过滤后的数据字典
    """
    if not cached_data:
        return {}

    end_time = datetime.now()
    start_time = end_time - timedelta(hours=hours)

    result = {}

    # 过滤攻击记录（根据时间戳）
    if data_type in ("attacks", "all"):
        attacks = cached_data.get("attacks", [])
        if attacks:
            filtered_attacks = []
            for attack in attacks:
                try:
                    attack_time = datetime.fromisoformat(attack.get("time", ""))
                    if start_time <= attack_time <= end_time:
                        filtered_attacks.append(attack)
                except (ValueError, TypeError):
                    # 如果时间解析失败，保留该记录（可能是旧格式）
                    filtered_attacks.append(attack)
            result["attacks"] = filtered_attacks
        else:
            result["attacks"] = []

    # 根据时间范围从hourly_trend重新计算summary
    if data_type in ("summary", "all"):
        trend_data = cached_data.get("hourly_trend", {})
        trend_hours = trend_data.get("hours", [])
        trend_counts = trend_data.get("counts", [])
        original_summary = cached_data.get("summary", {})

        # 如果hourly_trend为空，直接使用原始summary（可能是缓存数据本身的时间范围已经符合要求）
        if not trend_hours or not trend_counts:
            logger.warning(
                "[statistics] hourly_trend为空，直接使用原始summary数据，hours=%s",
                hours,
            )
            result["summary"] = original_summary
        else:
            # 计算时间范围内的总数
            total_requests = 0
            matched_count = 0
            for i, hour_label in enumerate(trend_hours):
                try:
                    # 尝试解析时间标签
                    if ":" in hour_label and len(hour_label) > 10:
                        # 5分钟粒度：YYYY-MM-DD HH:MM
                        hour_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:%M")
                    elif hour_label.endswith(":00"):
                        # 小时粒度：YYYY-MM-DD HH:00
                        hour_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:00")
                    else:
                        # 按天：YYYY-MM-DD
                        hour_dt = datetime.strptime(hour_label, "%Y-%m-%d")

                    if start_time <= hour_dt <= end_time:
                        total_requests += (
                            trend_counts[i] if i < len(trend_counts) else 0
                        )
                        matched_count += 1
                except (ValueError, TypeError) as e:
                    logger.debug(
                        "[statistics] 解析时间标签失败：hour_label=%s, error=%s",
                        hour_label,
                        e,
                    )
                    continue

            # 如果没有任何匹配的时间桶，说明缓存数据的时间范围不包含查询时间范围
            # 这种情况下，如果查询时间范围大于缓存时间范围，返回空数据
            # 如果查询时间范围小于缓存时间范围，可能是时间标签格式问题，使用原始summary
            if matched_count == 0:
                logger.warning(
                    "[statistics] 时间范围过滤后没有匹配的数据点，hours=%s, start_time=%s, end_time=%s, 原始数据点数量=%s",
                    hours,
                    start_time.isoformat(),
                    end_time.isoformat(),
                    len(trend_hours),
                )
                # 如果原始summary的总数不为0，说明有数据，可能是时间标签格式问题
                # 这种情况下，直接使用原始summary
                if original_summary.get("total_requests", 0) > 0:
                    logger.info(
                        "[statistics] 使用原始summary数据（时间标签可能不匹配）",
                    )
                    result["summary"] = original_summary
                else:
                    # 确实没有数据
                    result["summary"] = {
                        "total_requests": 0,
                        "success_requests": 0,
                        "error_requests": 0,
                        "error_rate": 0.0,
                        "attack_count": 0,
                        "error_log_count": 0,
                    }
            else:
                # 从原始summary中获取其他信息（错误率等需要从状态码分布计算）
                status_dist = cached_data.get("status_distribution", {})

                # 计算错误请求数和成功请求数（基于状态码分布）
                error_requests = sum(
                    int(count)
                    for status, count in status_dist.items()
                    if int(status) >= 400
                )
                success_requests = sum(
                    int(count)
                    for status, count in status_dist.items()
                    if 200 <= int(status) < 300
                )

                # 如果时间范围内的总数与原始总数不同，需要按比例调整
                original_total = original_summary.get("total_requests", 0)
                if original_total > 0 and total_requests != original_total:
                    # 按比例调整错误数和成功数
                    ratio = total_requests / original_total if original_total > 0 else 0
                    error_requests = int(error_requests * ratio)
                    success_requests = int(success_requests * ratio)

                error_rate = (
                    (error_requests / total_requests * 100)
                    if total_requests > 0
                    else 0.0
                )

                # error_log_count 无法从hourly_trend重新计算，按比例调整
                original_error_log_count = original_summary.get("error_log_count", 0)
                if original_total > 0 and total_requests != original_total:
                    # 按比例调整error_log_count
                    ratio = total_requests / original_total if original_total > 0 else 0
                    error_log_count = int(original_error_log_count * ratio)
                else:
                    error_log_count = original_error_log_count

                result["summary"] = {
                    "total_requests": total_requests,
                    "success_requests": success_requests,
                    "error_requests": error_requests,
                    "error_rate": round(error_rate, 2),
                    "attack_count": len(result.get("attacks", [])),
                    "error_log_count": error_log_count,
                }

    # Top IPs和Top Paths无法从hourly_trend重新计算，只能返回缓存中的汇总数据
    # 但至少可以确保返回的数据对应正确的时间范围
    if data_type in ("top_ips", "all"):
        result["top_ips"] = cached_data.get("top_ips", [])
    if data_type in ("top_paths", "all"):
        result["top_paths"] = cached_data.get("top_paths", [])
    if data_type in ("status_distribution", "all"):
        result["status_distribution"] = cached_data.get("status_distribution", {})
    if data_type in ("method_distribution", "all"):
        result["method_distribution"] = cached_data.get("method_distribution", {})

    return result


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
    - 1小时：从5分钟缓存中获取，按5分钟粒度展示
    - 24小时：从1天缓存中获取，按小时粒度展示
    - 7天：从1天缓存中聚合，按天粒度展示
    - 不在请求期间重新解析日志，只返回已缓存的数据
    """
    try:
        # 根据查询时间范围，决定从哪个缓存读取数据
        if hours <= 1:
            # 1小时：从5分钟缓存中获取，按5分钟展示
            cached_data = get_cached_statistics_5min(max_age_minutes=30)
        elif hours <= 24:
            # 24小时：从1小时缓存中获取，按小时展示
            cached_data = get_cached_statistics(1, max_age_minutes=30)
        else:
            # 7天：从1天缓存中获取，按天展示
            cached_data = get_cached_statistics(24, max_age_minutes=30)
        if not cached_data:
            logger.warning(
                "[statistics] 趋势数据查询失败：未找到缓存数据，hours=%s",
                hours,
            )
            return {
                "success": False,
                "time_range_hours": hours,
                "message": "趋势数据暂未生成，请稍后重试",
            }

        trend_data = cached_data.get("hourly_trend")
        if not trend_data:
            logger.warning(
                "[statistics] 趋势数据查询失败：缓存数据中没有 hourly_trend 字段，hours=%s, cached_keys=%s",
                hours,
                list(cached_data.keys()) if cached_data else [],
            )
            return {
                "success": False,
                "time_range_hours": hours,
                "message": "趋势数据暂未生成，请稍后重试",
            }

        trend_hours = trend_data.get("hours", [])
        trend_counts = trend_data.get("counts", [])

        logger.info(
            "[statistics] 趋势数据查询：hours=%s, 原始数据点数量=%s, 前5个时间点=%s",
            hours,
            len(trend_hours),
            trend_hours[:5] if trend_hours else [],
        )

        # 根据查询时间范围，聚合数据
        if hours <= 1:
            # 1小时：直接使用5分钟粒度数据（从5分钟缓存中获取）
            # 优先过滤最近1小时的数据，如果为空则返回所有可用数据
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)
            filtered_hours = []
            filtered_counts = []

            logger.debug(
                "[statistics] 1小时趋势过滤：start_time=%s, end_time=%s, 原始数据点=%s",
                start_time.isoformat(),
                end_time.isoformat(),
                len(trend_hours),
            )

            for i, hour_label in enumerate(trend_hours):
                try:
                    # 解析时间标签（5分钟粒度：YYYY-MM-DD HH:MM）
                    hour_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:%M")
                    if start_time <= hour_dt <= end_time:
                        filtered_hours.append(hour_label)
                        filtered_counts.append(
                            trend_counts[i] if i < len(trend_counts) else 0
                        )
                except Exception as e:
                    logger.warning(
                        "[statistics] 解析时间标签失败：hour_label=%s, error=%s",
                        hour_label,
                        e,
                    )
                    continue

            logger.info(
                "[statistics] 1小时趋势过滤结果：过滤后数据点数量=%s",
                len(filtered_hours),
            )

            return {
                "success": True,
                "time_range_hours": hours,
                "hourly_trend": {
                    "hours": filtered_hours,
                    "counts": filtered_counts,
                },
            }
        elif hours <= 24:
            # 24小时：直接使用小时粒度数据（从1小时缓存中获取）
            # 优先过滤最近24小时的数据，如果为空则返回所有可用数据
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)
            filtered_hours = []
            filtered_counts = []
            for i, hour_label in enumerate(trend_hours):
                try:
                    # 解析时间标签（小时粒度：YYYY-MM-DD HH:00）
                    hour_dt = datetime.strptime(hour_label, "%Y-%m-%d %H:00")
                    if start_time <= hour_dt <= end_time:
                        filtered_hours.append(hour_label)
                        filtered_counts.append(trend_counts[i])
                except Exception:
                    continue
            
            return {
                "success": True,
                "time_range_hours": hours,
                "hourly_trend": {
                    "hours": filtered_hours,
                    "counts": filtered_counts,
                },
            }
        else:
            # 7天：直接使用天粒度数据（从1天缓存中获取）
            # 1天缓存中已经是按天聚合的数据了
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)
            filtered_days = []
            filtered_counts = []
            
            for i, day_label in enumerate(trend_hours):
                try:
                    # 解析时间标签（天粒度：YYYY-MM-DD）
                    day_dt = datetime.strptime(day_label, "%Y-%m-%d")
                    if start_time <= day_dt <= end_time:
                        filtered_days.append(day_label)
                        filtered_counts.append(trend_counts[i] if i < len(trend_counts) else 0)
                except Exception:
                    continue
            
            return {
                "success": True,
                "time_range_hours": hours,
                "hourly_trend": {
                    "hours": filtered_days,
                    "counts": filtered_counts,
                },
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
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间重新解析日志
    """
    try:
        if hours <= 1:
            cached_data = get_cached_statistics_5min(max_age_minutes=30)
        else:
            cached_data = get_cached_statistics(24, max_age_minutes=30)

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
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间重新解析日志
    """
    try:
        if hours <= 1:
            cached_data = get_cached_statistics_5min(max_age_minutes=30)
        else:
            cached_data = get_cached_statistics(24, max_age_minutes=30)

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
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间重新解析日志
    """
    try:
        if hours <= 1:
            cached_data = get_cached_statistics_5min(max_age_minutes=30)
        else:
            cached_data = get_cached_statistics(24, max_age_minutes=30)

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
    - 只返回后台预先分析并缓存好的数据
    - 不在请求期间重新解析日志
    """
    try:
        if hours <= 1:
            cached_data = get_cached_statistics_5min(max_age_minutes=30)
        else:
            cached_data = get_cached_statistics(24, max_age_minutes=30)

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
