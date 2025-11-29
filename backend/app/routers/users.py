"""
用户管理路由
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel, Field

from app.database import get_db
from app.auth import get_current_user, hash_password, verify_password
from app.models import User
from app.utils.audit import create_audit_log, get_client_ip

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    """创建用户请求"""

    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    is_active: bool = Field(default=True, description="是否激活")


class UserUpdate(BaseModel):
    """更新用户请求"""

    username: Optional[str] = Field(
        None, min_length=3, max_length=50, description="用户名"
    )
    is_active: Optional[bool] = Field(None, description="是否激活")


class PasswordChange(BaseModel):
    """修改密码请求"""

    old_password: str = Field(..., min_length=1, description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class PasswordReset(BaseModel):
    """重置密码请求（管理员）"""

    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class UserResponse(BaseModel):
    """用户响应"""

    id: int
    username: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


@router.get("/", summary="获取用户列表")
async def get_users(
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取所有用户列表"""
    users = db.query(User).offset(skip).limit(limit).all()
    return {
        "success": True,
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
            for user in users
        ],
        "total": db.query(User).count(),
    }


@router.get("/{user_id}", summary="获取用户详情")
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定用户的详细信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    return {
        "success": True,
        "user": {
            "id": user.id,
            "username": user.username,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
    }


@router.post("/", summary="创建用户")
async def create_user(
    user_data: UserCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新用户"""
    # 检查用户名是否已存在
    existing_user = db.query(User).filter(User.username == user_data.username).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在"
        )

    # 创建新用户
    hashed_password = hash_password(user_data.password)
    new_user = User(
        username=user_data.username,
        password_hash=hashed_password,
        is_active=user_data.is_active,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="user_create",
            target=f"用户: {user_data.username}",
            details={"user_id": new_user.id, "username": new_user.username},
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "用户创建成功",
            "user": {
                "id": new_user.id,
                "username": new_user.username,
                "is_active": new_user.is_active,
                "created_at": (
                    new_user.created_at.isoformat() if new_user.created_at else None
                ),
            },
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建用户失败: {str(e)}",
        )


@router.put("/{user_id}", summary="更新用户信息")
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新用户信息"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 检查用户名是否已被其他用户使用
    if user_data.username and user_data.username != user.username:
        existing_user = (
            db.query(User).filter(User.username == user_data.username).first()
        )
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被使用"
            )
        user.username = user_data.username

    if user_data.is_active is not None:
        user.is_active = user_data.is_active

    try:
        db.commit()
        db.refresh(user)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="user_update",
            target=f"用户: {user.username}",
            details={"user_id": user.id, "changes": user_data.dict(exclude_unset=True)},
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "用户信息更新成功",
            "user": {
                "id": user.id,
                "username": user.username,
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            },
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被使用"
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新用户信息失败: {str(e)}",
        )


@router.delete("/{user_id}", summary="删除用户")
async def delete_user(
    user_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除用户"""
    # 不能删除自己
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除自己的账户"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    username = user.username

    try:
        db.delete(user)
        db.commit()

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="user_delete",
            target=f"用户: {username}",
            details={"deleted_user_id": user_id},
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "用户删除成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除用户失败: {str(e)}",
        )


@router.post("/me/change-password", summary="修改当前用户密码")
async def change_my_password(
    password_data: PasswordChange,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前用户修改自己的密码"""
    # 验证旧密码
    if not verify_password(password_data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="旧密码错误"
        )

    # 更新密码
    current_user.password_hash = hash_password(password_data.new_password)

    try:
        db.commit()

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="user_password_change",
            target="自己的账户",
            details={},
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "密码修改成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改密码失败: {str(e)}",
        )


@router.post("/{user_id}/change-password", summary="重置用户密码（管理员）")
async def reset_password(
    user_id: int,
    password_data: PasswordReset,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """管理员重置用户密码"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

    # 更新密码
    user.password_hash = hash_password(password_data.new_password)

    try:
        db.commit()

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="user_password_reset",
            target=f"用户: {user.username}",
            details={"user_id": user_id},
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "密码重置成功"}
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重置密码失败: {str(e)}",
        )
