"""
Nginx 配置管理路由
"""
from typing import Dict, Any
from pathlib import Path
import subprocess
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user, get_current_user_basic, User
from app.utils.nginx import (
    get_config_content,
    save_config_content,
    test_config,
    reload_nginx,
    get_nginx_status,
    get_config_path,
    _resolve_nginx_executable,
    format_config,
    validate_config,
)
from app.utils.nginx_versions import get_active_version
from app.utils.backup import create_backup, list_backups, restore_backup, get_backup
from app.utils.audit import create_audit_log, get_client_ip

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigUpdateRequest(BaseModel):
    """配置更新请求"""
    content: str


class ConfigRestoreRequest(BaseModel):
    """配置恢复请求"""
    backup_id: int


class ConfigFormatRequest(BaseModel):
    """配置格式化请求"""
    content: str


class ConfigValidateRequest(BaseModel):
    """配置校验请求"""
    content: str


@router.get("", summary="读取当前 Nginx 配置")
async def get_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """读取当前 Nginx 配置文件内容"""
    try:
        content = get_config_content()
        config_path = get_config_path()
        
        # 获取当前 Nginx 版本信息
        active = get_active_version()
        nginx_version = None
        nginx_version_detail = None
        
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
            "success": True,
            "content": content,
            "config_path": str(config_path),
            "nginx_version": nginx_version,
            "nginx_version_detail": nginx_version_detail,
            "active_version": active["version"] if active else None,
            "install_path": str(active["install_path"]) if active else None,
            "binary": str(nginx_executable) if nginx_executable else None
        }
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取配置失败: {str(e)}"
        )


@router.post("", summary="更新 Nginx 配置")
async def update_config(
    request_data: ConfigUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新 Nginx 配置文件（自动备份）"""
    try:
        # 先创建备份
        backup = create_backup(db, created_by_id=current_user.id)
        
        # 保存新配置
        save_config_content(request_data.content)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="config_update",
            target="nginx.conf",
            details={"backup_id": backup.id},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "配置已保存，已创建备份",
            "backup_id": backup.id
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存配置失败: {str(e)}"
        )


@router.post("/test", summary="测试配置有效性")
async def test_nginx_config(
    current_user: User = Depends(get_current_user)
):
    """测试 Nginx 配置是否有效（测试已保存的配置文件）"""
    result = test_config()
    return result


@router.post("/format", summary="格式化配置内容")
async def format_nginx_config(
    request_data: ConfigFormatRequest,
    current_user: User = Depends(get_current_user)
):
    """格式化 Nginx 配置内容（不保存）"""
    result = format_config(request_data.content)
    return result


@router.post("/validate", summary="校验配置内容")
async def validate_nginx_config(
    request_data: ConfigValidateRequest,
    current_user: User = Depends(get_current_user)
):
    """校验 Nginx 配置内容（不保存，使用临时文件测试）"""
    result = validate_config(request_data.content)
    return result


@router.post("/reload", summary="重新加载 Nginx 配置")
async def reload_nginx_config(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """重新加载 Nginx 配置"""
    # 先测试配置
    test_result = test_config()
    if not test_result["success"]:
        return {
            "success": False,
            "message": "配置测试失败，无法重载",
            "test_result": test_result
        }
    
    # 重载配置
    result = reload_nginx()
    
    # 记录操作日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="config_reload",
        target="nginx",
        details={"result": result["success"]},
        ip_address=get_client_ip(request)
    )
    
    return result


@router.get("/status", summary="获取 Nginx 运行状态")
async def get_status(
    current_user: User = Depends(get_current_user)
):
    """获取 Nginx 运行状态"""
    status_info = get_nginx_status()
    return status_info


@router.get("/backups", summary="获取备份列表")
async def get_config_backups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取所有配置备份列表"""
    # 默认最多返回 10 个备份版本，保持与配置中的 max_backups 一致
    backups = list_backups(db, limit=10)
    return {
        "success": True,
        "backups": [
            {
                "id": backup.id,
                "filename": backup.filename,
                "file_path": backup.file_path,
                "created_at": backup.created_at.isoformat() if backup.created_at else None,
                "created_by_id": backup.created_by_id
            }
            for backup in backups
        ]
    }


@router.post("/backup", summary="手动创建配置备份")
async def create_config_backup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """手动创建配置备份"""
    try:
        backup = create_backup(db, created_by_id=current_user.id)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="backup_create",
            target=backup.filename,
            details={"backup_id": backup.id},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "备份创建成功",
            "backup": {
                "id": backup.id,
                "filename": backup.filename,
                "file_path": backup.file_path,
                "created_at": backup.created_at.isoformat() if backup.created_at else None
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建备份失败: {str(e)}"
        )


@router.post("/restore/{backup_id}", summary="恢复指定备份")
async def restore_config_backup(
    backup_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """恢复指定备份的配置"""
    backup = get_backup(db, backup_id)
    if not backup:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="备份不存在"
        )
    
    try:
        # 恢复备份前先创建当前配置的备份
        current_backup = create_backup(db, created_by_id=current_user.id)
        
        # 恢复备份
        success = restore_backup(db, backup_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="恢复备份失败"
            )
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="backup_restore",
            target=backup.filename,
            details={"backup_id": backup_id, "current_backup_id": current_backup.id},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "配置已恢复",
            "backup_id": backup_id
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"恢复备份失败: {str(e)}"
        )

