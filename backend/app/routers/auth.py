"""
认证路由
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import (
    authenticate_user, create_user_token, get_current_user_basic,
    get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.models import User
from app.utils.audit import create_audit_log, get_client_ip

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str


class LoginResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    username: str
    expires_in: int


@router.post("/login", summary="用户登录")
def login(
    login_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """用户登录，返回 JWT token"""
    user = authenticate_user(db, login_data.username, login_data.password, request)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_user_token(user)

    # 记录登录日志
    create_audit_log(
        db=db,
        user_id=user.id,
        username=user.username,
        action="user_login",
        target=None,
        details={"result": True},
        ip_address=get_client_ip(request)
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/login-basic", summary="Basic 认证登录（返回 token）")
def login_basic(
    request: Request,
    user: User = Depends(get_current_user_basic),
    db: Session = Depends(get_db),
):
    """通过 Basic Auth 登录，返回 JWT token"""
    access_token = create_user_token(user)

    # 记录登录日志
    create_audit_log(
        db=db,
        user_id=user.id,
        username=user.username,
        action="user_login",
        target=None,
        details={"method": "basic", "result": True},
        ip_address=get_client_ip(request)
    )
    
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.get("/me", summary="获取当前用户信息")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取当前登录用户的信息"""
    from app.auth import verify_password
    
    # 检查是否是默认密码（admin/admin）
    is_default_password = False
    if current_user.username == "admin":
        # 验证密码是否是默认密码 "admin"
        is_default_password = verify_password("admin", current_user.password_hash)
    
    return {
        "success": True,
        "user": {
            "id": current_user.id,
            "username": current_user.username,
            "is_active": current_user.is_active,
            "is_admin": current_user.is_admin,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
            "is_default_password": is_default_password
        }
    }
