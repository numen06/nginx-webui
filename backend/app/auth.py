"""
认证模块
实现 HTTP Basic Authentication 和 JWT token 管理
"""
import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials, HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.config import get_config

# HTTP Basic Auth 安全对象
security_basic = HTTPBasic()

# HTTP Bearer Token 安全对象
security_bearer = HTTPBearer()

# JWT 配置
SECRET_KEY = None  # 将从配置文件读取
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 小时


def get_secret_key() -> str:
    """获取 JWT 密钥"""
    global SECRET_KEY
    if SECRET_KEY is None:
        config = get_config()
        SECRET_KEY = config.app.secret_key or "change-this-secret-key-in-production"
    return SECRET_KEY


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def hash_password(password: str) -> str:
    """加密密码"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建 JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
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


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """验证用户凭据"""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_current_user_basic(credentials: HTTPBasicCredentials = Depends(security_basic), db: Session = Depends(get_db)) -> User:
    """通过 Basic Auth 获取当前用户"""
    user = authenticate_user(db, credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return user


def get_current_user_token(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)) -> dict:
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


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security_bearer), db: Session = Depends(get_db)) -> User:
    """获取当前用户（通过 Token）"""
    payload = get_current_user_token(credentials)
    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 token",
        )
    
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )
    return user


def get_user_by_token(token: str, db: Session) -> Optional[User]:
    """通过 token 获取用户对象"""
    payload = verify_token(token)
    if payload is None:
        return None
    
    username: str = payload.get("sub")
    if username is None:
        return None
    
    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        return None
    return user

