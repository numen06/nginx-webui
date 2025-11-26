"""
Nginx 日志查看路由
"""
from typing import Optional, List
from pathlib import Path
from datetime import datetime
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
    access_pattern = r'\[(\d{2}/\w{3}/\d{4}):(\d{2}:\d{2}:\d{2})\s*[+-]?\d{4}\]'
    match = re.search(access_pattern, log_line)
    if match:
        date_str = match.group(1) + ':' + match.group(2)
        try:
            return datetime.strptime(date_str, '%d/%b/%Y:%H:%M:%S')
        except ValueError:
            pass
    
    # Nginx 错误日志格式: 2024/11/26 10:00:00
    error_patterns = [
        r'(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2}:\d{2})',
        r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',
        r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})',
    ]
    
    for pattern in error_patterns:
        match = re.search(pattern, log_line)
        if match:
            date_str = match.group(1)
            for fmt in ['%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S']:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
    
    return None


def filter_logs(
    lines: List[str],
    keyword: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None
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
    end_date: Optional[datetime] = None
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
            "error": f"日志文件不存在: {log_path}"
        }
    
    try:
        # 读取所有行
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = [line.rstrip('\n') for line in f.readlines()]
        
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
            "end_line": end
        }
    except Exception as e:
        return {
            "success": False,
            "lines": [],
            "total_lines": 0,
            "filtered_lines": 0,
            "error": f"读取日志文件失败: {str(e)}"
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


def _resolve_access_log_path() -> str:
    """
    解析当前应当读取的访问日志路径。

    优先级：
    1. 优先使用配置文件中的 nginx.access_log 路径（这是nginx实际使用的路径）
    2. 如果配置文件中的路径不存在，尝试从当前运行版本的安装目录读取
    """
    config = get_config()
    
    # 优先使用配置文件中的路径
    config_log_path = _resolve_log_path(config.nginx.access_log)
    config_log_file = Path(config_log_path)
    
    if config_log_file.exists():
        return config_log_path
    
    # 如果配置文件中的路径不存在，尝试从版本安装目录读取
    active = get_active_version()
    if active is not None:
        candidate = active["install_path"] / "logs" / "access.log"
        if candidate.exists():
            return str(candidate.resolve())
    
    # 如果都不存在，仍然返回配置的路径（让调用者处理错误）
    return config_log_path


def _resolve_error_log_path() -> str:
    """
    解析当前应当读取的错误日志路径。

    优先级：
    1. 优先使用配置文件中的 nginx.error_log 路径（这是nginx实际使用的路径）
    2. 如果配置文件中的路径不存在，尝试从当前运行版本的安装目录读取
    """
    config = get_config()
    
    # 优先使用配置文件中的路径
    config_log_path = _resolve_log_path(config.nginx.error_log)
    config_log_file = Path(config_log_path)
    
    if config_log_file.exists():
        return config_log_path
    
    # 如果配置文件中的路径不存在，尝试从版本安装目录读取
    active = get_active_version()
    if active is not None:
        candidate = active["install_path"] / "logs" / "error.log"
        if candidate.exists():
            return str(candidate.resolve())
    
    # 如果都不存在，仍然返回配置的路径（让调用者处理错误）
    return config_log_path


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
        nginx_version = "系统安装版本"
    
    # 尝试获取详细的版本信息
    try:
        if nginx_executable and Path(nginx_executable).exists():
            version_result = subprocess.run(
                [str(nginx_executable), "-v"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if version_result.stderr:
                nginx_version_detail = version_result.stderr.strip()
    except Exception:
        pass
    
    return {
        "nginx_version": nginx_version,
        "nginx_version_detail": nginx_version_detail,
        "active_version": active["version"] if active else None,
        "install_path": str(active["install_path"]) if active else None,
        "binary": str(nginx_executable) if nginx_executable else None
    }


@router.get("/access", summary="查看访问日志")
async def get_access_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=50000, description="每页行数"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
    current_user: User = Depends(get_current_user)
):
    """查看 Nginx 访问日志（优先使用当前运行版本的日志文件）"""
    log_path = _resolve_access_log_path()
    
    # 解析日期参数
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            start_date = start_date.replace('+', ' ')
            # 尝试多种日期格式
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
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
                detail=f"开始日期格式错误: {str(e)}"
            )
    
    if end_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            end_date = end_date.replace('+', ' ')
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    parsed_end_date = datetime.strptime(end_date, fmt)
                    # 如果是日期格式，设置为当天最后一秒
                    if fmt == '%Y-%m-%d':
                        parsed_end_date = parsed_end_date.replace(hour=23, minute=59, second=59)
                    break
                except ValueError:
                    continue
            if not parsed_end_date:
                raise ValueError(f"无效的结束日期格式: {end_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"结束日期格式错误: {str(e)}"
            )
    
    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size
    
    result = read_log_file(
        log_path,
        lines=page_size,
        offset=offset,
        keyword=keyword,
        start_date=parsed_start_date,
        end_date=parsed_end_date
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败")
        )
    
    # 计算总页数（基于过滤后的行数）
    filtered_lines = result.get("filtered_lines", result["total_lines"])
    total_pages = (filtered_lines + page_size - 1) // page_size if filtered_lines > 0 else 1
    
    # 获取 Nginx 版本信息
    version_info = _get_nginx_version_info()
    
    return {
        "success": True,
        "logs": result["lines"],
        "log_path": log_path,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "filtered_lines": filtered_lines,
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0)
        },
        **version_info
    }


@router.get("/error", summary="查看错误日志")
async def get_error_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=50000, description="每页行数"),
    keyword: Optional[str] = Query(None, description="关键词搜索"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS)"),
    current_user: User = Depends(get_current_user)
):
    """查看 Nginx 错误日志（优先使用当前运行版本的日志文件）"""
    log_path = _resolve_error_log_path()
    
    # 解析日期参数
    parsed_start_date = None
    parsed_end_date = None
    
    if start_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            start_date = start_date.replace('+', ' ')
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
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
                detail=f"开始日期格式错误: {str(e)}"
            )
    
    if end_date:
        try:
            # URL解码（处理空格被编码为+的情况）
            end_date = end_date.replace('+', ' ')
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    parsed_end_date = datetime.strptime(end_date, fmt)
                    if fmt == '%Y-%m-%d':
                        parsed_end_date = parsed_end_date.replace(hour=23, minute=59, second=59)
                    break
                except ValueError:
                    continue
            if not parsed_end_date:
                raise ValueError(f"无效的结束日期格式: {end_date}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"结束日期格式错误: {str(e)}"
            )
    
    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size
    
    result = read_log_file(
        log_path,
        lines=page_size,
        offset=offset,
        keyword=keyword,
        start_date=parsed_start_date,
        end_date=parsed_end_date
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败")
        )
    
    # 计算总页数（基于过滤后的行数）
    filtered_lines = result.get("filtered_lines", result["total_lines"])
    total_pages = (filtered_lines + page_size - 1) // page_size if filtered_lines > 0 else 1
    
    # 获取 Nginx 版本信息
    version_info = _get_nginx_version_info()
    
    return {
        "success": True,
        "logs": result["lines"],
        "log_path": log_path,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "filtered_lines": filtered_lines,
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0)
        },
        **version_info
    }

