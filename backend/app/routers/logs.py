"""
Nginx 日志查看路由
"""

from typing import Optional, List
from pathlib import Path
from datetime import datetime
import os
import subprocess
import re
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.utils.nginx_versions import get_active_version
from app.utils.nginx import _resolve_nginx_executable

router = APIRouter(prefix="/api/logs", tags=["logs"])


def parse_log_date(log_line: str) -> Optional[datetime]:
    """
    从日志行中解析日期

    支持常见格式：
    - Nginx 访问日志: [26/Nov/2024:10:00:00 +0800]
    - Nginx 错误日志: 2024/11/26 10:00:00
    - 其他格式尝试多种解析
    """
    # Nginx 访问日志格式: [26/Nov/2024:10:00:00 +0800]
    access_pattern = r"\[(\d{2}/\w{3}/\d{4}):(\d{2}:\d{2}:\d{2})\s*[+-]?\d{4}\]"
    match = re.search(access_pattern, log_line)
    if match:
        date_str = match.group(1) + ":" + match.group(2)
        try:
            return datetime.strptime(date_str, "%d/%b/%Y:%H:%M:%S")
        except ValueError:
            pass

    # Nginx 错误日志格式: 2024/11/26 10:00:00
    error_patterns = [
        r"(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})",
        r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})",
        r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})",
    ]

    for pattern in error_patterns:
        match = re.search(pattern, log_line)
        if match:
            date_str = match.group(1)
            for fmt in ["%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

    return None


def filter_logs(
    lines: List[str],
    keyword: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> List[str]:
    """
    过滤日志行

    Args:
        lines: 日志行列表
        keyword: 关键词（如果提供，只返回包含关键词的行）
        start_date: 开始日期（如果提供，只返回该日期之后的日志）
        end_date: 结束日期（如果提供，只返回该日期之前的日志）

    Returns:
        过滤后的日志行列表
    """
    filtered = []

    for line in lines:
        # 关键词过滤
        if keyword and keyword.lower() not in line.lower():
            continue

        # 日期过滤
        if start_date or end_date:
            log_date = parse_log_date(line)
            if log_date:
                if start_date and log_date < start_date:
                    continue
                if end_date and log_date > end_date:
                    continue

        filtered.append(line)

    return filtered


def read_log_file(
    log_path: str,
    lines: int = 100,
    offset: int = 0,
    keyword: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> dict:
    """
    读取日志文件

    Args:
        log_path: 日志文件路径
        lines: 读取行数（如果提供了过滤条件，这是过滤后的行数）
        offset: 从文件末尾偏移的行数（0 表示最后 N 行）
        keyword: 关键词搜索
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        {
            "success": bool,
            "lines": List[str],
            "total_lines": int,
            "filtered_lines": int  # 过滤后的总行数
        }
    """
    log_file = Path(log_path)

    if not log_file.exists():
        return {
            "success": False,
            "lines": [],
            "total_lines": 0,
            "filtered_lines": 0,
            "error": f"日志文件不存在: {log_path}",
        }

    try:
        # 为了避免超大日志文件一次性读入内存，这里只读取文件末尾的最多 max_lines_cap 行，
        # 实现“分片加载”的效果。对于常规使用（查看最近日志）来说已经足够。
        max_lines_cap = 2000  # 安全上限，可根据需要调整

        # 读取日志尾部内容（最多 max_lines_cap 行）
        def _read_tail(path: Path, max_lines: int) -> list[str]:
            if not path.exists():
                return []
            try:
                with open(path, "rb") as f:
                    f.seek(0, 2)
                    file_size = f.tell()

                    # 小文件直接读完
                    if file_size < 1024 * 1024:  # < 1MB
                        with open(path, "r", encoding="utf-8", errors="ignore") as f2:
                            return [line.rstrip("\n") for line in f2.readlines()]

                    lines_buf: list[str] = []
                    buffer_size = min(8192, file_size)
                    position = file_size
                    buffer = b""

                    while len(lines_buf) < max_lines and position > 0:
                        read_size = min(buffer_size, position)
                        position -= read_size
                        f.seek(position)
                        chunk = f.read(read_size)
                        buffer = chunk + buffer

                        while b"\n" in buffer and len(lines_buf) < max_lines:
                            line, buffer = buffer.rsplit(b"\n", 1)
                            try:
                                lines_buf.insert(
                                    0, line.decode("utf-8", errors="ignore")
                                )
                            except Exception:
                                pass

                        if position == 0:
                            if buffer:
                                try:
                                    lines_buf.insert(
                                        0, buffer.decode("utf-8", errors="ignore")
                                    )
                                except Exception:
                                    pass
                            break

                    return (
                        lines_buf[-max_lines:]
                        if len(lines_buf) > max_lines
                        else lines_buf
                    )
            except Exception:
                # 回退到简单读取（仍然限制最大行数，避免一次性读入超大文件）
                try:
                    from collections import deque as _deque

                    tail = _deque(maxlen=max_lines)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f2:
                        for line in f2:
                            tail.append(line.rstrip("\n"))
                    return list(tail)
                except Exception:
                    return []

        all_lines = _read_tail(log_file, max_lines_cap)

        # total_lines 以当前截取的行数为准（即最近 max_lines_cap 行）
        # 对于非常大的日志文件，早期的旧日志不会被包含在分页结果中
        total_lines = len(all_lines)

        # 应用过滤条件
        filtered_lines = all_lines
        if keyword or start_date or end_date:
            filtered_lines = filter_logs(all_lines, keyword, start_date, end_date)

        filtered_total = len(filtered_lines)

        # 计算要返回的行范围（基于过滤后的结果）
        if offset == 0:
            # 返回最后 N 行
            start = max(0, filtered_total - lines)
            end = filtered_total
        else:
            # 从指定偏移量开始
            start = max(0, filtered_total - offset - lines)
            end = max(0, filtered_total - offset)

        selected_lines = filtered_lines[start:end]

        return {
            "success": True,
            "lines": selected_lines,
            "total_lines": total_lines,
            "filtered_lines": filtered_total,
            "start_line": start + 1,
            "end_line": end,
        }
    except Exception as e:
        return {
            "success": False,
            "lines": [],
            "total_lines": 0,
            "filtered_lines": 0,
            "error": f"读取日志文件失败: {str(e)}",
        }


def _resolve_log_path(config_path: str) -> str:
    """
    解析日志文件路径，将相对路径转换为绝对路径。

    Args:
        config_path: 配置中的日志路径（可能是相对路径或绝对路径）

    Returns:
        解析后的绝对路径字符串
    """
    log_path = Path(config_path)

    # 如果已经是绝对路径，直接返回
    if log_path.is_absolute():
        return str(log_path.resolve())

    # 相对路径需要解析：相对于 backend 目录
    # 当前文件在 backend/app/routers/logs.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    resolved_path = (backend_dir / config_path).resolve()

    return str(resolved_path)


def _parse_log_path_from_nginx_config(
    config_path: Path, log_type: str = "access_log"
) -> Optional[str]:
    """
    从nginx配置文件中解析日志路径

    Args:
        config_path: nginx配置文件路径
        log_type: 日志类型，'access_log' 或 'error_log'

    Returns:
        解析出的日志路径，如果未找到或为off则返回None
    """
    if not config_path.exists():
        return None

    try:
        content = config_path.read_text(encoding="utf-8")
        # 匹配 access_log 或 error_log 配置行
        # 支持格式：access_log /path/to/log; 或 access_log logs/access.log;
        pattern = rf"{log_type}\s+([^;]+);"
        match = re.search(pattern, content)

        if match:
            log_path_str = match.group(1).strip()
            # 如果是 off，返回 None
            if log_path_str.lower() == "off":
                return None

            # 如果是绝对路径，直接返回
            log_path = Path(log_path_str)
            if log_path.is_absolute():
                return str(log_path.resolve())

            # 如果是相对路径，相对于nginx配置文件所在目录解析
            # nginx配置中的相对路径是相对于nginx运行目录（通常是安装目录）
            config_dir = config_path.parent
            # 如果配置文件在 conf/ 目录下，安装目录应该是 conf 的父目录
            if config_dir.name == "conf":
                install_path = config_dir.parent
                resolved = (install_path / log_path).resolve()
                return str(resolved)
            else:
                resolved = (config_dir / log_path).resolve()
                return str(resolved)
    except Exception:
        pass

    return None


def _resolve_access_log_path() -> str:
    """
    解析当前应当读取的访问日志路径。

    如果检测到运行中的nginx版本，优先使用该版本安装目录下的logs/access.log。
    否则使用配置文件中的路径。
    """
    # 如果检测到运行中的nginx版本，优先使用安装目录下的日志
    active = get_active_version()
    if active is not None:
        # 优先使用nginx安装目录下的logs/access.log
        default_path = active["install_path"] / "logs" / "access.log"
        if default_path.exists():
            return str(default_path.resolve())
        # 即使不存在也返回nginx安装目录下的路径（让调用者处理错误）
        return str(default_path.resolve())

    # 如果没有运行中的nginx版本，使用配置文件中的路径
    config = get_config()
    return _resolve_log_path(config.nginx.access_log)


def _resolve_error_log_path() -> str:
    """
    解析当前应当读取的错误日志路径。

    如果检测到运行中的nginx版本，优先使用该版本安装目录下的logs/error.log。
    否则使用配置文件中的路径。
    """
    # 如果检测到运行中的nginx版本，优先使用安装目录下的日志
    active = get_active_version()
    if active is not None:
        # 优先使用nginx安装目录下的logs/error.log
        default_path = active["install_path"] / "logs" / "error.log"
        if default_path.exists():
            return str(default_path.resolve())
        # 即使不存在也返回nginx安装目录下的路径（让调用者处理错误）
        return str(default_path.resolve())

    # 如果没有运行中的nginx版本，使用配置文件中的路径
    config = get_config()
    return _resolve_log_path(config.nginx.error_log)


def _get_nginx_version_info() -> dict:
    """获取当前 Nginx 版本信息"""
    active = get_active_version()
    nginx_version = None
    nginx_version_detail = None
    nginx_executable = None

    if active is not None:
        # 使用多版本管理的 Nginx
        nginx_version = active["version"]
        nginx_executable = active["executable"]
    else:
        # 使用系统 Nginx
        nginx_executable = _resolve_nginx_executable()
        nginx_version = (
            "系统安装版本"
            if nginx_executable and nginx_executable.exists()
            else "未安装"
        )

    # 尝试获取详细的版本信息
    try:
        if nginx_executable and nginx_executable.exists():
            version_result = subprocess.run(
                [str(nginx_executable), "-v"], capture_output=True, text=True, timeout=5
            )
            if version_result.stderr:
                nginx_version_detail = version_result.stderr.strip()
    except Exception:
        pass

    return {
        "nginx_version": nginx_version,
        "nginx_version_detail": nginx_version_detail,
        "active_version": active["version"] if active else None,
        "install_path": active["directory"] if active else None,  # 使用目录简称
        "binary": str(nginx_executable) if nginx_executable else None,
    }


@router.get("/access", summary="查看访问日志")
async def get_access_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=50000, description="每页行数"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[str] = Query(
        None, description="开始日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"
    ),
    end_date: Optional[str] = Query(
        None, description="结束日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"
    ),
    current_user: User = Depends(get_current_user),
):
    """查看 Nginx 访问日志（优先使用当前运行版本的日志文件）"""
    log_path = _resolve_access_log_path()

    # 解析日期参数
    parsed_start_date = None
    parsed_end_date = None

    if start_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            start_date = start_date.replace("+", " ")
            # 尝试多种日期格式
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    parsed_start_date = datetime.strptime(start_date, fmt)
                    break
                except ValueError:
                    continue
            if not parsed_start_date:
                raise ValueError(f"无效的开始日期格式: {start_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"开始日期格式错误: {str(e)}",
            )

    if end_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            end_date = end_date.replace("+", " ")
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    parsed_end_date = datetime.strptime(end_date, fmt)
                    # 如果是日期格式，设置为当天最后一秒
                    if fmt == "%Y-%m-%d":
                        parsed_end_date = parsed_end_date.replace(
                            hour=23, minute=59, second=59
                        )
                    break
                except ValueError:
                    continue
            if not parsed_end_date:
                raise ValueError(f"无效的结束日期格式: {end_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"结束日期格式错误: {str(e)}",
            )

    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size

    result = read_log_file(
        log_path,
        lines=page_size,
        offset=offset,
        keyword=keyword,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败"),
        )

    # 计算总页数（基于过滤后的行数）
    filtered_lines = result.get("filtered_lines", result["total_lines"])
    total_pages = (
        (filtered_lines + page_size - 1) // page_size if filtered_lines > 0 else 1
    )

    # 获取 Nginx 版本信息
    version_info = _get_nginx_version_info()

    # 获取日志文件大小（字节）
    try:
        log_size_bytes = os.path.getsize(log_path)
    except OSError:
        log_size_bytes = None

    return {
        "success": True,
        "logs": result["lines"],
        "log_path": log_path,
        "log_size_bytes": log_size_bytes,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "filtered_lines": filtered_lines,
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0),
        },
        **version_info,
    }


@router.get("/error", summary="查看错误日志")
async def get_error_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=50000, description="每页行数"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[str] = Query(
        None, description="开始日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"
    ),
    end_date: Optional[str] = Query(
        None, description="结束日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"
    ),
    current_user: User = Depends(get_current_user),
):
    """查看 Nginx 错误日志（优先使用当前运行版本的日志文件）"""
    log_path = _resolve_error_log_path()

    # 解析日期参数
    parsed_start_date = None
    parsed_end_date = None

    if start_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            start_date = start_date.replace("+", " ")
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    parsed_start_date = datetime.strptime(start_date, fmt)
                    break
                except ValueError:
                    continue
            if not parsed_start_date:
                raise ValueError(f"无效的开始日期格式: {start_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"开始日期格式错误: {str(e)}",
            )

    if end_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            end_date = end_date.replace("+", " ")
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    parsed_end_date = datetime.strptime(end_date, fmt)
                    if fmt == "%Y-%m-%d":
                        parsed_end_date = parsed_end_date.replace(
                            hour=23, minute=59, second=59
                        )
                    break
                except ValueError:
                    continue
            if not parsed_end_date:
                raise ValueError(f"无效的结束日期格式: {end_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"结束日期格式错误: {str(e)}",
            )

    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size

    result = read_log_file(
        log_path,
        lines=page_size,
        offset=offset,
        keyword=keyword,
        start_date=parsed_start_date,
        end_date=parsed_end_date,
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败"),
        )

    # 计算总页数（基于过滤后的行数）
    filtered_lines = result.get("filtered_lines", result["total_lines"])
    total_pages = (
        (filtered_lines + page_size - 1) // page_size if filtered_lines > 0 else 1
    )

    # 获取 Nginx 版本信息
    version_info = _get_nginx_version_info()

    # 获取日志文件大小（字节）
    try:
        log_size_bytes = os.path.getsize(log_path)
    except OSError:
        log_size_bytes = None

    return {
        "success": True,
        "logs": result["lines"],
        "log_path": log_path,
        "log_size_bytes": log_size_bytes,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "filtered_lines": filtered_lines,
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0),
        },
        **version_info,
    }
