"""
Nginx 配置管理路由
"""

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
    has_pending_config_changes,
    apply_working_config,
)
from app.utils.nginx_status_cache import (
    get_cached_nginx_status,
    set_cached_nginx_status,
    clear_nginx_status_cache,
)
from app.utils.nginx_versions import get_active_version
from app.utils.backup import (
    create_backup,
    list_backups,
    restore_backup,
    get_backup,
    set_last_version,
)
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
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
            nginx_version = (
                "系统安装版本"
                if nginx_executable and nginx_executable.exists()
                else "未安装"
            )

        # 尝试获取详细的版本信息
        try:
            if nginx_executable and nginx_executable.exists():
                version_result = subprocess.run(
                    [str(nginx_executable), "-v"],
                    capture_output=True,
                    text=True,
                    timeout=5,
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
            "install_path": active["directory"] if active else None,  # 使用目录简称
            "binary": str(nginx_executable) if nginx_executable else None,
            "pending_changes": has_pending_config_changes(),
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取配置失败: {str(e)}",
        )


@router.post("", summary="更新 Nginx 配置")
async def update_config(
    request_data: ConfigUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新 Nginx 配置文件（仅写入工作副本）"""
    try:
        save_config_content(request_data.content)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="config_update",
            target="nginx.conf",
            details={"mode": "working_copy"},
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "配置已保存到临时副本，请校验并重载后生效",
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存配置失败: {str(e)}",
        )


@router.post("/test", summary="测试配置有效性")
async def test_nginx_config(current_user: User = Depends(get_current_user)):
    """测试 Nginx 配置是否有效（测试已保存的配置文件）"""
    result = test_config()
    return result


@router.post("/format", summary="格式化配置内容")
async def format_nginx_config(
    request_data: ConfigFormatRequest, current_user: User = Depends(get_current_user)
):
    """格式化 Nginx 配置内容（不保存）"""
    result = format_config(request_data.content)
    return result


@router.post("/validate", summary="校验配置内容")
async def validate_nginx_config(
    request_data: ConfigValidateRequest, current_user: User = Depends(get_current_user)
):
    """校验 Nginx 配置内容（不保存，使用临时文件测试）"""
    result = validate_config(request_data.content)
    return result


@router.post("/reload", summary="重新加载 Nginx 配置")
async def reload_nginx_config(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重新加载 Nginx 配置"""
    # 先测试配置
    test_result = test_config()
    if not test_result["success"]:
        return {
            "success": False,
            "message": "配置测试失败，无法重载",
            "test_result": test_result,
        }

    # 重载配置
    # 重载前：备份当前线上配置（覆盖前的版本，1号版本）
    backup_before = create_backup(db, created_by_id=current_user.id)

    # 应用工作副本并重载
    # 注意：apply_working_config()将工作副本（2号版本）复制到实际配置文件
    apply_working_config()
    result = reload_nginx()

    # 重载成功后：备份当前线上配置（此时已经是新配置了，2号版本）并标记为最后版本
    # 注意：apply_working_config()已经将工作副本复制到实际配置文件，
    # reload_nginx()已经重载了nginx，所以此时实际配置文件就是当前线上运行的配置（2号版本）
    # 最后版本应该始终是线上版本的备份，所以备份实际配置文件
    if result["success"]:
        # 备份实际配置文件（2号版本），因为这就是当前线上运行的配置
        backup_after = create_backup(
            db, created_by_id=current_user.id, is_last_version=True
        )

        # 确保工作副本和实际配置文件同步（工作副本 = 实际配置文件 = 2号版本）
        from app.utils.nginx import sync_working_config_from_actual

        sync_working_config_from_actual()

        result["backup_id"] = backup_before.id
        result["last_version_backup_id"] = backup_after.id
    else:
        result["backup_id"] = backup_before.id

    # 清除状态缓存（重载后状态可能变化）
    clear_nginx_status_cache()

    # 记录操作日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="config_reload",
        target="nginx",
        details={
            "result": result["success"],
            "backup_id": backup_before.id,
            "last_version_backup_id": backup_after.id if result["success"] else None,
        },
        ip_address=get_client_ip(request),
    )

    return result


@router.post("/apply", summary="强制覆盖配置文件（不重载nginx）")
async def apply_config(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    强制覆盖配置文件（应用工作副本到实际配置）

    功能：
    1. 先测试配置有效性
    2. 将工作副本覆盖到实际配置文件
    3. 不重载nginx（需要手动重启nginx才能生效）
    注意：此操作不会创建备份，只有重载nginx时才会创建备份

    适用场景：
    - 需要修改配置但暂时不想重载nginx
    - 准备在后续手动重启nginx时生效
    - 批量修改配置时的中间步骤
    """
    # 先测试配置
    test_result = test_config()
    if not test_result["success"]:
        return {
            "success": False,
            "message": "配置测试失败，无法覆盖",
            "test_result": test_result,
        }

    try:
        # 应用工作副本到实际配置文件
        # 注意：不创建备份，因为配置还没有真正生效（nginx未重载）
        # 只有在重载nginx时才会创建备份
        actual_config_path = apply_working_config()

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="config_apply",
            target="nginx",
            details={
                "config_path": str(actual_config_path),
            },
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "配置文件已覆盖，建议重启 Nginx 使配置生效",
            "config_path": str(actual_config_path),
            "need_restart": True,  # 标记需要重启
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"覆盖配置失败: {str(e)}",
        }


@router.get("/status", summary="获取 Nginx 运行状态")
async def get_status(
    force_refresh: bool = False,
    current_user: User = Depends(get_current_user),
):
    """
    获取 Nginx 运行状态（使用缓存优化性能）

    Args:
        force_refresh: 强制刷新，不使用缓存
    """
    # 尝试从缓存获取
    if not force_refresh:
        cached_status = get_cached_nginx_status()
        if cached_status is not None:
            return cached_status

    # 缓存未命中或强制刷新，重新获取状态
    status_info = get_nginx_status()

    # 保存到缓存
    set_cached_nginx_status(status_info)

    return status_info


@router.get("/backups", summary="获取备份列表")
async def get_config_backups(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
                "created_at": (
                    backup.created_at.isoformat() if backup.created_at else None
                ),
                "created_by_id": backup.created_by_id,
                "is_last_version": backup.is_last_version,
            }
            for backup in backups
        ],
    }


@router.post("/backup", summary="手动创建配置备份（备份当前线上配置）")
async def create_config_backup(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动创建配置备份（备份当前正在生效的 nginx.conf，而非编辑器中的临时配置）"""
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
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "备份创建成功",
            "backup": {
                "id": backup.id,
                "filename": backup.filename,
                "file_path": backup.file_path,
                "created_at": (
                    backup.created_at.isoformat() if backup.created_at else None
                ),
            },
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建备份失败: {str(e)}",
        )


@router.get("/backup/{backup_id}/content", summary="获取备份内容")
async def get_backup_content(
    backup_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定备份的配置内容"""
    backup = get_backup(db, backup_id)
    if not backup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份不存在")

    try:
        from pathlib import Path

        backup_path = Path(backup.file_path)
        if not backup_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="备份文件不存在"
            )

        # 读取备份文件内容
        with open(backup_path, "r", encoding="utf-8") as f:
            content = f.read()

        return {
            "success": True,
            "content": content,
            "backup_id": backup_id,
            "filename": backup.filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取备份内容失败: {str(e)}",
        )


@router.post("/restore/{backup_id}", summary="恢复指定备份")
async def restore_config_backup(
    backup_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """恢复指定备份的配置"""
    backup = get_backup(db, backup_id)
    if not backup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="备份不存在")

    try:
        # 直接恢复备份（不再为当前配置创建新的备份）
        success = restore_backup(db, backup_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="恢复备份失败"
            )

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="backup_restore",
            target=backup.filename,
            details={"backup_id": backup_id},
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "配置已恢复", "backup_id": backup_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"恢复备份失败: {str(e)}",
        )
