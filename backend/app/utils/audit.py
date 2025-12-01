"""
操作日志记录工具
"""
import json
from datetime import datetime
from typing import Optional, Dict, Any
from functools import wraps
from fastapi import Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OperationLog, User


def create_audit_log(
    db: Session,
    user_id: Optional[int],
    username: str,
    action: str,
    target: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None
) -> OperationLog:
    """
    创建操作日志记录
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        username: 用户名
        action: 操作类型
        target: 操作目标（如文件路径、配置名等）
        details: 操作详情（字典格式）
        ip_address: 客户端IP地址
    
    Returns:
        OperationLog: 创建的操作日志记录
    """
    log = OperationLog(
        user_id=user_id,
        username=username,
        action=action,
        target=target,
        details=json.dumps(details, ensure_ascii=False) if details else None,
        ip_address=ip_address,
        timestamp=datetime.now()
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def get_client_ip(request: Request) -> Optional[str]:
    """从请求中获取客户端IP地址"""
    # 检查 X-Forwarded-For 头（代理/负载均衡器）
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    
    # 检查 X-Real-IP 头
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    # 使用客户端IP
    if request.client:
        return request.client.host
    
    return None


def log_operation(action: str, target: Optional[str] = None):
    """
    操作日志装饰器
    
    Args:
        action: 操作类型
        target: 操作目标（可以是函数参数名，函数会从参数中获取值）
    
    Usage:
        @log_operation("config_update", target="config_content")
        async def update_config(config_content: str, ...):
            pass
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从参数中提取请求对象和用户信息
            request: Optional[Request] = None
            current_user = None
            db: Optional[Session] = None
            
            # 查找 Request 参数
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if request is None:
                request = kwargs.get('request')
            
            # 查找 current_user 参数
            for arg in args:
                if hasattr(arg, 'username'):  # 假设是 User 对象
                    current_user = arg
                    break
            
            if current_user is None:
                current_user = kwargs.get('current_user')
            
            # 查找 db 参数
            for arg in args:
                if isinstance(arg, Session):
                    db = arg
                    break
            
            if db is None:
                db = kwargs.get('db')
            
            # 如果找不到 db，从依赖注入获取
            if db is None:
                db_gen = get_db()
                db = next(db_gen)
                need_close = True
            else:
                need_close = False
            
            try:
                # 获取用户名和用户ID
                username = "unknown"
                user_id = None
                if current_user:
                    if hasattr(current_user, 'username'):
                        username = current_user.username
                    if hasattr(current_user, 'id'):
                        user_id = current_user.id
                    elif isinstance(current_user, dict):
                        username = current_user.get('sub', 'unknown')
                
                # 获取操作目标
                operation_target = target
                if target and target in kwargs:
                    operation_target = str(kwargs[target])
                
                # 获取客户端IP
                ip_address = None
                if request:
                    ip_address = get_client_ip(request)
                
                # 构建操作详情
                details = {}
                if request:
                    details['method'] = request.method
                    details['path'] = str(request.url.path)
                
                # 执行原函数
                result = await func(*args, **kwargs)
                
                # 记录操作日志
                try:
                    create_audit_log(
                        db=db,
                        user_id=user_id,
                        username=username,
                        action=action,
                        target=operation_target,
                        details=details,
                        ip_address=ip_address
                    )
                except Exception as e:
                    # 日志记录失败不应影响主流程
                    print(f"记录操作日志失败: {e}")
                
                return result
            finally:
                if need_close:
                    db.close()
        
        return wrapper
    return decorator

