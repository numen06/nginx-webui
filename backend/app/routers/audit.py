"""
操作日志查询路由
"""
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.database import get_db
from app.auth import get_current_user, User
from app.models import OperationLog

router = APIRouter(prefix="/api/audit", tags=["audit"])


class CleanupLogsRequest(BaseModel):
    """日志清理请求模型"""
    retain_days: int = Field(
        default=90,
        ge=1,
        le=3650,
        description="需要保留的天数，默认 90 天"
    )


@router.get("/logs", summary="查询操作日志")
async def get_audit_logs(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量"),
    username: Optional[str] = Query(None, description="按用户名筛选"),
    action: Optional[str] = Query(None, description="按操作类型筛选"),
    start_time: Optional[str] = Query(None, description="开始时间 (ISO 格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO 格式)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """查询操作日志"""
    query = db.query(OperationLog)
    
    # 应用筛选条件
    filters = []
    
    if username:
        filters.append(OperationLog.username == username)
    
    if action:
        filters.append(OperationLog.action == action)
    
    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            filters.append(OperationLog.timestamp >= start_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的开始时间格式，请使用 ISO 格式"
            )
    
    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            filters.append(OperationLog.timestamp <= end_dt)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的结束时间格式，请使用 ISO 格式"
            )
    
    if filters:
        query = query.filter(and_(*filters))
    
    # 获取总数
    total = query.count()
    
    # 分页查询
    logs = query.order_by(OperationLog.timestamp.desc()).offset((page - 1) * page_size).limit(page_size).all()
    
    # 计算总页数
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    
    return {
        "success": True,
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "username": log.username,
                "action": log.action,
                "target": log.target,
                "details": log.details,
                "ip_address": log.ip_address,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None
            }
            for log in logs
        ],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages
        }
    }


@router.post("/logs/cleanup", summary="清理操作日志", status_code=status.HTTP_200_OK)
async def cleanup_audit_logs(
    payload: CleanupLogsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """清理早于指定天数的操作日志"""
    retain_days = payload.retain_days
    cutoff_time = datetime.now() - timedelta(days=retain_days)
    
    deleted_count = (
        db.query(OperationLog)
        .filter(OperationLog.timestamp < cutoff_time)
        .delete(synchronize_session=False)
    )
    
    db.commit()
    
    return {
        "success": True,
        "message": f"已清理 {deleted_count} 条日志，保留最近 {retain_days} 天记录",
        "deleted": deleted_count,
        "retain_days": retain_days
    }

