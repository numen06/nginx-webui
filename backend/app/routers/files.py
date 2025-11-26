"""
静态文件管理路由
"""
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.utils.audit import create_audit_log, get_client_ip
from app.utils.nginx_versions import _get_versions_root, _get_install_path

router = APIRouter(prefix="/api/files", tags=["files"])


class FileInfo(BaseModel):
    """文件信息"""
    name: str
    path: str
    is_dir: bool
    size: int
    modified_time: Optional[str] = None


class RenameRequest(BaseModel):
    """重命名请求"""
    new_name: str


class MoveRequest(BaseModel):
    """移动请求"""
    destination: str


class MkdirRequest(BaseModel):
    """创建目录请求"""
    name: str


def get_version_root_dir(version: Optional[str] = None) -> Path:
    """
    获取指定 Nginx 版本的根目录（html 目录）
    
    Args:
        version: Nginx 版本号，如果为 None 则使用当前活动版本
    
    Returns:
        Path: Nginx 版本的 html 目录绝对路径
    
    Raises:
        HTTPException: 如果版本不存在或未编译
    """
    if version:
        install_path = _get_install_path(version)
        if not install_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nginx 版本 {version} 不存在"
            )
        html_dir = install_path / "html"
        if not html_dir.exists():
            html_dir.mkdir(parents=True, exist_ok=True)
        return html_dir
    else:
        # 如果没有指定版本，尝试使用当前活动版本
        from app.utils.nginx_versions import get_active_version
        active = get_active_version()
        if active:
            html_dir = active["install_path"] / "html"
            if not html_dir.exists():
                html_dir.mkdir(parents=True, exist_ok=True)
            return html_dir
        else:
            # 如果没有活动版本，使用第一个已编译的版本
            versions_root = _get_versions_root()
            if not versions_root.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="未找到任何 Nginx 版本"
                )
            # 查找第一个已编译的版本（有 sbin/nginx 文件）
            for child in sorted(versions_root.iterdir()):
                if child.is_dir():
                    executable = child / "sbin" / "nginx"
                    if executable.exists():
                        html_dir = child / "html"
                        if not html_dir.exists():
                            html_dir.mkdir(parents=True, exist_ok=True)
                        return html_dir
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到任何已编译的 Nginx 版本"
            )


def validate_path(relative_path: Optional[str], version: Optional[str] = None) -> Path:
    """
    验证并规范化文件路径，防止目录遍历攻击
    
    Args:
        relative_path: 相对路径
        version: Nginx 版本号
    
    Returns:
        Path: 规范化后的绝对路径
    
    Raises:
        HTTPException: 如果路径无效或超出允许范围
    """
    root_dir = get_version_root_dir(version)
    
    # 规范化相对路径
    if relative_path:
        # 移除前导和尾随的斜杠
        relative_path = relative_path.strip('/')
        # 移除路径中的 .. 和 .
        normalized = os.path.normpath(relative_path)
        if '..' in normalized or normalized.startswith('/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的路径"
            )
        target_path = root_dir / normalized
    else:
        target_path = root_dir
    
    # 确保路径在根目录内
    try:
        target_path.resolve().relative_to(root_dir.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="路径超出允许范围"
        )
    
    return target_path


@router.get("", summary="列出静态文件")
async def list_files(
    path: Optional[str] = Query(None, description="目录路径（相对路径）"),
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user)
):
    """列出指定目录下的文件"""
    try:
        root_dir = get_version_root_dir(version)
        target_path = validate_path(path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目录不存在"
            )
        
        if not target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径不是目录"
            )
        
        files = []
        for item in target_path.iterdir():
            stat = item.stat()
            files.append(FileInfo(
                name=item.name,
                path=str(item.relative_to(root_dir)),
                is_dir=item.is_dir(),
                size=stat.st_size if item.is_file() else 0,
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat()
            ))
        
        # 按名称排序（目录在前）
        files.sort(key=lambda x: (not x.is_dir, x.name))
        
        return {
            "success": True,
            "files": [f.dict() for f in files],
            "path": path or "",
            "version": version
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出文件失败: {str(e)}"
        )


@router.post("/upload", summary="上传文件")
async def upload_file(
    request: Request,
    path: Optional[str] = Form(None, description="上传到的目录路径（相对路径）"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上传文件到指定目录"""
    try:
        root_dir = get_version_root_dir(version)
        target_dir = validate_path(path, version)
        
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        
        uploaded_files = []
        for file in files:
            # 验证文件名
            filename = file.filename
            if not filename or '/' in filename or '..' in filename:
                continue
            
            file_path = target_dir / filename
            
            # 保存文件
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
            
            uploaded_files.append({
                "filename": filename,
                "path": str(file_path.relative_to(root_dir)),
                "size": len(content)
            })
            
            # 记录操作日志
            create_audit_log(
                db=db,
                user_id=current_user.id,
                username=current_user.username,
                action="file_upload",
                target=str(file_path.relative_to(root_dir)),
                details={"filename": filename, "size": len(content), "version": version},
                ip_address=get_client_ip(request)
            )
        
        return {
            "success": True,
            "message": f"成功上传 {len(uploaded_files)} 个文件",
            "files": uploaded_files
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文件失败: {str(e)}"
        )


@router.get("/{file_path:path}", summary="获取文件内容")
async def get_file(
    file_path: str,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user)
):
    """获取文件内容"""
    try:
        target_path = validate_path(file_path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在"
            )
        
        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径是目录，不是文件"
            )
        
        # 读取文件内容
        with open(target_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        return {
            "success": True,
            "content": content,
            "path": file_path
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取文件失败: {str(e)}"
        )


@router.put("/{file_path:path}", summary="修改文件内容")
async def update_file(
    file_path: str,
    request: Request,
    content: str = Form(...),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改文件内容"""
    try:
        target_path = validate_path(file_path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在"
            )
        
        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径是目录，不是文件"
            )
        
        # 保存文件内容
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="file_update",
            target=file_path,
            details={"size": len(content), "version": version},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "文件已更新"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新文件失败: {str(e)}"
        )


@router.delete("/{file_path:path}", summary="删除文件或目录")
async def delete_file(
    file_path: str,
    request: Request,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除文件或目录"""
    try:
        target_path = validate_path(file_path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件或目录不存在"
            )
        
        # 删除文件或目录
        if target_path.is_dir():
            shutil.rmtree(target_path)
            action = "dir_delete"
        else:
            target_path.unlink()
            action = "file_delete"
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action=action,
            target=file_path,
            details={"version": version},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败: {str(e)}"
        )


@router.post("/mkdir", summary="创建目录")
async def create_directory(
    request: Request,
    path: Optional[str] = Form(None, description="父目录路径（相对路径）"),
    name: str = Form(..., description="目录名称"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建目录"""
    try:
        root_dir = get_version_root_dir(version)
        parent_dir = validate_path(path, version)
        new_dir = parent_dir / name
        
        # 验证新目录路径
        relative_path = str(new_dir.relative_to(root_dir))
        validate_path(relative_path, version)
        
        if new_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目录已存在"
            )
        
        new_dir.mkdir(parents=True, exist_ok=False)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dir_create",
            target=relative_path,
            details={"name": name, "version": version},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "目录创建成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建目录失败: {str(e)}"
        )


@router.post("/rename/{file_path:path}", summary="重命名文件或目录")
async def rename_file(
    file_path: str,
    request: Request,
    new_name: str = Form(...),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """重命名文件或目录"""
    try:
        root_dir = get_version_root_dir(version)
        target_path = validate_path(file_path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件或目录不存在"
            )
        
        # 验证新名称
        if '/' in new_name or '..' in new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件名"
            )
        
        new_path = target_path.parent / new_name
        
        # 验证新路径
        relative_path = str(new_path.relative_to(root_dir))
        validate_path(relative_path, version)
        
        if new_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标文件名已存在"
            )
        
        target_path.rename(new_path)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="file_rename",
            target=file_path,
            details={"new_name": new_name, "version": version},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "重命名成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重命名失败: {str(e)}"
        )


@router.get("/download/{file_path:path}", summary="下载文件")
async def download_file(
    file_path: str,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    current_user: User = Depends(get_current_user)
):
    """下载文件"""
    try:
        target_path = validate_path(file_path, version)
        
        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文件不存在"
            )
        
        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法下载目录"
            )
        
        return FileResponse(
            path=str(target_path),
            filename=target_path.name,
            media_type='application/octet-stream'
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载文件失败: {str(e)}"
        )

