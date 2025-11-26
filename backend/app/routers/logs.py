"""
Nginx 日志查看路由
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from pathlib import Path

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config

router = APIRouter(prefix="/api/logs", tags=["logs"])


def read_log_file(log_path: str, lines: int = 100, offset: int = 0) -> dict:
    """
    读取日志文件
    
    Args:
        log_path: 日志文件路径
        lines: 读取行数
        offset: 从文件末尾偏移的行数（0 表示最后 N 行）
    
    Returns:
        {
            "success": bool,
            "lines": List[str],
            "total_lines": int
        }
    """
    log_file = Path(log_path)
    
    if not log_file.exists():
        return {
            "success": False,
            "lines": [],
            "total_lines": 0,
            "error": f"日志文件不存在: {log_path}"
        }
    
    try:
        # 读取所有行
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # 计算要返回的行范围
        if offset == 0:
            # 返回最后 N 行
            start = max(0, total_lines - lines)
            end = total_lines
        else:
            # 从指定偏移量开始
            start = max(0, total_lines - offset - lines)
            end = max(0, total_lines - offset)
        
        selected_lines = all_lines[start:end]
        
        return {
            "success": True,
            "lines": [line.rstrip('\n') for line in selected_lines],
            "total_lines": total_lines,
            "start_line": start + 1,
            "end_line": end
        }
    except Exception as e:
        return {
            "success": False,
            "lines": [],
            "total_lines": 0,
            "error": f"读取日志文件失败: {str(e)}"
        }


@router.get("/access", summary="查看访问日志")
async def get_access_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=1000, description="每页行数"),
    current_user: User = Depends(get_current_user)
):
    """查看 Nginx 访问日志"""
    config = get_config()
    log_path = config.nginx.access_log
    
    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size
    
    result = read_log_file(log_path, lines=page_size, offset=offset)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败")
        )
    
    # 计算总页数
    total_pages = (result["total_lines"] + page_size - 1) // page_size if result["total_lines"] > 0 else 1
    
    return {
        "success": True,
        "logs": result["lines"],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0)
        }
    }


@router.get("/error", summary="查看错误日志")
async def get_error_log(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(100, ge=1, le=1000, description="每页行数"),
    current_user: User = Depends(get_current_user)
):
    """查看 Nginx 错误日志"""
    config = get_config()
    log_path = config.nginx.error_log
    
    # 计算偏移量（从文件末尾）
    offset = (page - 1) * page_size
    
    result = read_log_file(log_path, lines=page_size, offset=offset)
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "读取日志失败")
        )
    
    # 计算总页数
    total_pages = (result["total_lines"] + page_size - 1) // page_size if result["total_lines"] > 0 else 1
    
    return {
        "success": True,
        "logs": result["lines"],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_lines": result["total_lines"],
            "total_pages": total_pages,
            "start_line": result.get("start_line", 0),
            "end_line": result.get("end_line", 0)
        }
    }

