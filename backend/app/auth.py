"""
认证模块
实现 HTTP Basic Authentication 和 JWT token 管理
"""

import bcrypt
from hashlib import sha256
from threading import Lock
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Query, Request
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from sqlalchemy.orm import Session

from app.database import get_db, get_or_create_private_secret
from app.models import OperationLog, User
from app.utils.audit import create_audit_log, get_client_ip
from app.config import get_config

# HTTP Basic Auth 安全对象
security_basic = HTTPBasic()

# HTTP Bearer Token 安全对象
security_bearer = HTTPBearer()

# JWT 配置
SECRET_KEY = None  # 将从配置文件读取
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
LOGIN_FAILURE_LIMIT = 10
LOGIN_FAILURE_WINDOW = timedelta(minutes=5)
login_lock = Lock()


def get_secret_key() -> str:
    """获取 JWT 密钥"""
    global SECRET_KEY
    if SECRET_KEY is None:
        config = get_config()
        configured_secret = config.app.secret_key
        if not configured_secret or configured_secret == "change-this-secret-key-in-production":
            configured_secret = get_or_create_private_secret("jwt-secret")
        SECRET_KEY = configured_secret
    return SECRET_KEY


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def hash_password(password: str) -> str:
    """加密密码"""
    password_bytes = password.encode("utf-8")
    classes = sum((
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() and not c.isspace() for c in password),
    ))
    if len(password) < 12 or len(password_bytes) > 72 or classes < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码至少 12 个字符且不超过 72 字节，需包含大写、小写、数字、符号中的至少三类",
        )
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[dict]:
    """验证 JWT token"""
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def authenticate_user(db: Session, username: str, password: str, request: Request) -> Optional[User]:
    """在所有口令认证入口统一限制连续失败，并记录认证失败。"""
    ip_address = get_client_ip(request)
    with login_lock:
        failures = (
            db.query(OperationLog.id)
            .filter(
                OperationLog.action == "user_login_failed",
                OperationLog.ip_address == ip_address,
                OperationLog.timestamp >= datetime.now() - LOGIN_FAILURE_WINDOW,
            )
            .limit(LOGIN_FAILURE_LIMIT)
            .count()
        )
        if failures >= LOGIN_FAILURE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="登录失败次数过多，请稍后重试",
                headers={"Retry-After": str(int(LOGIN_FAILURE_WINDOW.total_seconds()))},
            )

        user = db.query(User).filter(User.username == username).first()
        if user and user.is_active and verify_password(password, user.password_hash):
            return user
        create_audit_log(
            db=db, user_id=user.id if user else None, username=username[:50],
            action="user_login_failed", details={"result": False}, ip_address=ip_address,
        )
        return None


def create_user_token(user: User) -> str:
    return create_access_token({"sub": user.username, "pwd": sha256(user.password_hash.encode()).hexdigest()})


def _token_user(payload: dict, db: Session) -> Optional[User]:
    username = payload.get("sub")
    if not username:
        return None
    user = db.query(User).filter(User.username == username, User.is_active.is_(True)).first()
    if user and payload.get("pwd") == sha256(user.password_hash.encode()).hexdigest():
        return user
    return None


def get_current_user_basic(
    request: Request,
    credentials: HTTPBasicCredentials = Depends(security_basic),
    db: Session = Depends(get_db),
) -> User:
    """通过 Basic Auth 获取当前用户"""
    user = authenticate_user(db, credentials.username, credentials.password, request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_user_token(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
) -> dict:
    """通过 Token 获取当前用户信息"""
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 token 或 token 已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_bearer),
    db: Session = Depends(get_db),
) -> User:
    """获取当前用户（通过 Token）"""
    payload = get_current_user_token(credentials)
    user = _token_user(payload, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效，请重新登录")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Require an active administrator for privileged management APIs."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user


def get_user_by_token(token: str, db: Session) -> Optional[User]:
    """通过 token 获取用户对象"""
    payload = verify_token(token)
    return _token_user(payload, db) if payload else None


def get_current_user_optional_query(
    token: Optional[str] = Query(None, description="身份验证 Token（可选）"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
    db: Session = Depends(get_db),
) -> User:
    """
    获取当前用户，支持两种方式：
    1. Authorization header (Bearer token) - 优先
    2. Query parameter (?token=xxx) - 备用，用于下载链接
    """
    if credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少身份验证信息")
    user = get_user_by_token(token, db)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话已失效，请重新登录")
    return user
