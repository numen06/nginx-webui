"""
静态文件管理路由
"""
import os
import shutil
import tarfile
import zipfile
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

BACKEND_ROOT = Path(__file__).resolve().parents[2]

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


def get_version_install_dir(version: Optional[str] = None) -> Path:
    """
    获取指定 Nginx 版本的安装目录
    
    Args:
        version: Nginx 版本号，如果为 None 则使用当前活动版本
    
    Returns:
        Path: Nginx 版本的安装目录绝对路径
    
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
        return install_path
    else:
        # 如果没有指定版本，尝试使用当前活动版本
        from app.utils.nginx_versions import get_active_version
        active = get_active_version()
        if active:
            return active["install_path"]
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
                        return child
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到任何已编译的 Nginx 版本"
            )


def _resolve_config_path(path_str: str) -> Path:
    """将配置中的相对路径解析为绝对路径"""
    path = Path(path_str)
    if not path.is_absolute():
        path = (BACKEND_ROOT / path).resolve()
    return path


def get_version_root_dir(version: Optional[str] = None, root_only: bool = False) -> Path:
    """
    获取指定 Nginx 版本的文件管理根目录
    
    Args:
        version: Nginx 版本号，如果为 None 则使用当前活动版本
        root_only: 如果为 True，返回整个安装目录；如果为 False，返回统一的静态目录
    
    Returns:
        Path: Nginx 版本的文件管理根目录绝对路径
    
    Raises:
        HTTPException: 如果版本不存在或未编译
    """
    if root_only:
        return get_version_install_dir(version)
    
    config = get_config()
    static_dir = _resolve_config_path(config.nginx.static_dir)
    static_dir.mkdir(parents=True, exist_ok=True)
    return static_dir


def validate_path(relative_path: Optional[str], version: Optional[str] = None, root_only: bool = False) -> Path:
    """
    验证并规范化文件路径，防止目录遍历攻击
    
    Args:
        relative_path: 相对路径
        version: Nginx 版本号
        root_only: 如果为 True，使用整个安装目录；如果为 False，使用 html 目录
    
    Returns:
        Path: 规范化后的绝对路径
    
    Raises:
        HTTPException: 如果路径无效或超出允许范围
    """
    root_dir = get_version_root_dir(version, root_only)
    
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
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user)
):
    """列出指定目录下的文件"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        target_path = validate_path(path, version, root_only)
        
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
            "version": version,
            "root_only": root_only,
            "root_path": str(root_dir)
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
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """上传文件到指定目录"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        target_dir = validate_path(path, version, root_only)
        
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
                details={
                    "filename": filename,
                    "size": len(content),
                    "version": version,
                    "root_only": root_only
                },
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


def get_packages_dir() -> Path:
    """
    获取静态资源包存储目录
    
    Returns:
        Path: 资源包存储目录的绝对路径
    """
    config = get_config()
    # 使用备份目录的父目录下的 packages 目录
    backup_dir = Path(config.backup.backup_dir)
    packages_dir = backup_dir.parent / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)
    return packages_dir


@router.post("/upload-package", summary="上传静态资源包（仅保存，不解压）")
async def upload_package(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传静态资源包到服务器（仅保存，不解压）
    
    支持的格式：
    - .zip
    - .tar.gz / .tgz
    - .tar
    """
    try:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未选择文件"
            )
        
        # 验证文件格式
        filename_lower = file.filename.lower()
        if not any(filename_lower.endswith(ext) for ext in ['.zip', '.tar.gz', '.tgz', '.tar']):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar"
            )
        
        # 获取资源包存储目录
        packages_dir = get_packages_dir()
        
        # 保存文件（如果同名文件已存在，添加时间戳）
        file_path = packages_dir / file.filename
        if file_path.exists():
            # 添加时间戳避免覆盖
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            stem = file_path.stem
            suffix = file_path.suffix
            if stem.endswith('.tar') and suffix == '.gz':
                # 处理 .tar.gz 的情况
                stem = stem[:-4]
                suffix = '.tar.gz'
            file_path = packages_dir / f"{stem}_{timestamp}{suffix}"
        
        # 保存文件
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_upload",
            target=file_path.name,
            details={
                "filename": file.filename,
                "saved_as": file_path.name,
                "size": len(content)
            },
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "资源包上传成功",
            "filename": file_path.name,
            "size": len(content)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传资源包失败: {str(e)}"
        )


@router.get("/packages", summary="列出已上传的静态资源包")
async def list_packages(
    current_user: User = Depends(get_current_user)
):
    """列出已上传的静态资源包"""
    try:
        packages_dir = get_packages_dir()
        
        if not packages_dir.exists():
            return {
                "success": True,
                "packages": []
            }
        
        packages = []
        for file_path in sorted(packages_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if file_path.is_file():
                stat = file_path.stat()
                filename_lower = file_path.name.lower()
                is_valid = any(filename_lower.endswith(ext) for ext in ['.zip', '.tar.gz', '.tgz', '.tar'])
                if is_valid:
                    packages.append({
                        "filename": file_path.name,
                        "size": stat.st_size,
                        "uploaded_time": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
        
        return {
            "success": True,
            "packages": packages
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出资源包失败: {str(e)}"
        )


@router.delete("/packages/{filename}", summary="删除已上传的静态资源包")
async def delete_package(
    filename: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除已上传的静态资源包"""
    try:
        # 验证文件名，防止目录遍历
        if '/' in filename or '..' in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件名"
            )
        
        packages_dir = get_packages_dir()
        file_path = packages_dir / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资源包不存在"
            )
        
        # 删除文件
        file_path.unlink()
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_delete",
            target=filename,
            details={},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "资源包已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除资源包失败: {str(e)}"
        )




class PackageInfo(BaseModel):
    """资源包信息"""
    filename: str
    size: int
    uploaded_time: str


@router.post("/upload-package", summary="上传静态资源包（仅保存，不解压）")
async def upload_package(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    上传静态资源包到服务器（仅保存，不解压）
    
    支持的格式：
    - .zip
    - .tar.gz / .tgz
    - .tar
    """
    try:
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="未选择文件"
            )
        
        filename_lower = file.filename.lower()
        if not (filename_lower.endswith('.zip') or 
                filename_lower.endswith('.tar.gz') or 
                filename_lower.endswith('.tgz') or 
                filename_lower.endswith('.tar')):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar"
            )
        
        packages_dir = get_packages_dir()
        file_path = packages_dir / file.filename
        
        # 如果文件已存在，添加时间戳后缀
        if file_path.exists():
            import time
            name_parts = file.filename.rsplit('.', 1)
            if len(name_parts) == 2:
                file.filename = f"{name_parts[0]}_{int(time.time())}.{name_parts[1]}"
            else:
                file.filename = f"{file.filename}_{int(time.time())}"
            file_path = packages_dir / file.filename
        
        # 保存文件
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_upload",
            target=file.filename,
            details={"size": len(content)},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": f"资源包上传成功: {file.filename}",
            "filename": file.filename
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传资源包失败: {str(e)}"
        )


@router.get("/packages", summary="列出已上传的静态资源包")
async def list_packages(
    current_user: User = Depends(get_current_user)
):
    """列出所有已上传的静态资源包"""
    try:
        packages_dir = get_packages_dir()
        
        if not packages_dir.exists():
            return {
                "success": True,
                "packages": []
            }
        
        packages = []
        for file_path in packages_dir.iterdir():
            if file_path.is_file():
                filename_lower = file_path.name.lower()
                if (filename_lower.endswith('.zip') or 
                    filename_lower.endswith('.tar.gz') or 
                    filename_lower.endswith('.tgz') or 
                    filename_lower.endswith('.tar')):
                    stat = file_path.stat()
                    packages.append(PackageInfo(
                        filename=file_path.name,
                        size=stat.st_size,
                        uploaded_time=datetime.fromtimestamp(stat.st_mtime).isoformat()
                    ))
        
        # 按上传时间倒序排序
        packages.sort(key=lambda x: x.uploaded_time, reverse=True)
        
        return {
            "success": True,
            "packages": [p.dict() for p in packages]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出资源包失败: {str(e)}"
        )


@router.delete("/packages/{filename}", summary="删除已上传的静态资源包")
async def delete_package(
    filename: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除已上传的静态资源包"""
    try:
        # 验证文件名，防止目录遍历攻击
        if '/' in filename or '..' in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件名"
            )
        
        packages_dir = get_packages_dir()
        file_path = packages_dir / filename
        
        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="资源包不存在"
            )
        
        # 确保文件在 packages 目录内
        try:
            file_path.resolve().relative_to(packages_dir.resolve())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的文件路径"
            )
        
        # 删除文件
        file_path.unlink()
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_delete",
            target=filename,
            details={},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "资源包已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除资源包失败: {str(e)}"
        )


@router.post("/deploy-package", summary="部署静态资源包到 html 目录")
async def deploy_package(
    request: Request,
    filename: Optional[str] = Form(None, description="已上传的资源包文件名（如果提供则使用已上传的文件）"),
    file: Optional[UploadFile] = File(None, description="新上传的文件（如果提供则使用新文件）"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    extract_to_subdir: bool = Form(False, description="是否解压到子目录（使用包名）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    部署静态资源包（zip/tar.gz）到指定 Nginx 版本的 html 目录
    
    支持的格式：
    - .zip
    - .tar.gz / .tgz
    - .tar
    
    可以使用已上传的文件（通过 filename 参数）或新上传的文件（通过 file 参数）
    """
    try:
        # 确定使用哪个文件
        if filename:
            # 使用已上传的文件
            if '/' in filename or '..' in filename:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无效的文件名"
                )
            packages_dir = get_packages_dir()
            package_path = packages_dir / filename
            if not package_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"资源包 {filename} 不存在"
                )
            tmp_path = package_path
            original_filename = filename
            # 读取文件内容用于日志记录
            with open(package_path, 'rb') as f:
                content = f.read()
        elif file and file.filename:
            # 使用新上传的文件
            original_filename = file.filename
            # 保存上传的文件到临时目录
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_path = Path(tmp_file.name)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请提供已上传的文件名或上传新文件"
            )
        
        try:
            # 获取 html 目录
            html_dir = get_version_root_dir(version, root_only=False)
            
            # 确定解压目标目录
            if extract_to_subdir:
                # 使用包名（不含扩展名）作为子目录名
                package_name = Path(original_filename).stem
                if package_name.endswith('.tar'):
                    package_name = package_name[:-4]
                target_dir = html_dir / package_name
            else:
                target_dir = html_dir
            
            # 确保目标目录存在
            target_dir.mkdir(parents=True, exist_ok=True)
            
            # 根据文件类型解压
            filename_lower = original_filename.lower()
            if filename_lower.endswith('.zip'):
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    zip_ref.extractall(target_dir)
            elif filename_lower.endswith(('.tar.gz', '.tgz')):
                with tarfile.open(tmp_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(target_dir)
            elif filename_lower.endswith('.tar'):
                with tarfile.open(tmp_path, 'r') as tar_ref:
                    tar_ref.extractall(target_dir)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar"
                )
            
            # 记录操作日志
            create_audit_log(
                db=db,
                user_id=current_user.id,
                username=current_user.username,
                action="package_deploy",
                target=str(target_dir.relative_to(html_dir)),
                details={
                    "filename": original_filename,
                    "size": len(content),
                    "version": version,
                    "extract_to_subdir": extract_to_subdir,
                    "from_uploaded": bool(filename)
                },
                ip_address=get_client_ip(request)
            )
            
            return {
                "success": True,
                "message": f"静态资源包已成功部署到 {target_dir.relative_to(html_dir)}",
                "target_dir": str(target_dir.relative_to(html_dir))
            }
        finally:
            # 清理临时文件（仅当是新上传的文件时）
            if not filename and tmp_path.exists():
                tmp_path.unlink()
                
    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP 文件格式错误或已损坏"
        )
    except tarfile.TarError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TAR 文件格式错误: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"部署静态资源包失败: {str(e)}"
        )


@router.get("/{file_path:path}", summary="获取文件内容")
async def get_file(
    file_path: str,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user)
):
    """获取文件内容"""
    try:
        target_path = validate_path(file_path, version, root_only)
        
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
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改文件内容"""
    try:
        target_path = validate_path(file_path, version, root_only)
        
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
                details={"size": len(content), "version": version, "root_only": root_only},
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
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除文件或目录"""
    try:
        target_path = validate_path(file_path, version, root_only)
        
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
                details={"version": version, "root_only": root_only},
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
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建目录"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        parent_dir = validate_path(path, version, root_only)
        new_dir = parent_dir / name
        
        # 验证新目录路径
        relative_path = str(new_dir.relative_to(root_dir))
        validate_path(relative_path, version, root_only)
        
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
                details={"name": name, "version": version, "root_only": root_only},
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
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """重命名文件或目录"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        target_path = validate_path(file_path, version, root_only)
        
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
        validate_path(relative_path, version, root_only)
        
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
                details={"new_name": new_name, "version": version, "root_only": root_only},
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
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user)
):
    """下载文件"""
    try:
        target_path = validate_path(file_path, version, root_only)
        
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

