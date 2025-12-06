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
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Query,
    Request,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.auth import get_current_user, get_current_user_optional_query, User
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
                detail=f"Nginx 版本 {version} 不存在",
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
                    detail="未找到任何 Nginx 版本",
                )
            # 查找第一个已编译的版本（有 sbin/nginx 文件）
            for child in sorted(versions_root.iterdir()):
                if child.is_dir():
                    executable = child / "sbin" / "nginx"
                    if executable.exists():
                        return child
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未找到任何已编译的 Nginx 版本",
            )


def get_version_root_dir(
    version: Optional[str] = None, root_only: bool = False
) -> Path:
    """
    获取指定 Nginx 版本的文件管理根目录

    Args:
        version: Nginx 版本号，如果为 None 则使用当前活动版本
        root_only: 如果为 True，返回整个安装目录；如果为 False，返回 html 目录

    Returns:
        Path: Nginx 版本的文件管理根目录绝对路径

    Raises:
        HTTPException: 如果版本不存在或未编译
    """
    install_path = get_version_install_dir(version)

    if root_only:
        return install_path
    else:
        html_dir = install_path / "html"
        if not html_dir.exists():
            html_dir.mkdir(parents=True, exist_ok=True)
        return html_dir


def validate_path(
    relative_path: Optional[str], version: Optional[str] = None, root_only: bool = False
) -> Path:
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
        relative_path = relative_path.strip("/")
        # 移除路径中的 .. 和 .
        normalized = os.path.normpath(relative_path)
        if ".." in normalized or normalized.startswith("/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的路径"
            )
        target_path = root_dir / normalized
    else:
        target_path = root_dir

    # 确保路径在根目录内
    try:
        target_path.resolve().relative_to(root_dir.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="路径超出允许范围"
        )

    return target_path


@router.get("", summary="列出静态文件")
async def list_files(
    path: Optional[str] = Query(None, description="目录路径（相对路径）"),
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
):
    """列出指定目录下的文件"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        target_path = validate_path(path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="目录不存在"
            )

        if not target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="指定路径不是目录"
            )

        files = []
        for item in target_path.iterdir():
            stat = item.stat()
            files.append(
                FileInfo(
                    name=item.name,
                    path=str(item.relative_to(root_dir)),
                    is_dir=item.is_dir(),
                    size=stat.st_size if item.is_file() else 0,
                    # 统一使用本地时间的标准格式（YYYY-MM-DD HH:mm:ss）
                    modified_time=datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                )
            )

        # 按名称排序（目录在前）
        files.sort(key=lambda x: (not x.is_dir, x.name))

        return {
            "success": True,
            "files": [f.dict() for f in files],
            "path": path or "",
            "version": version,
            "root_only": root_only,
            "root_path": str(root_dir),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出文件失败: {str(e)}",
        )


@router.post("/upload", summary="上传文件")
async def upload_file(
    request: Request,
    path: Optional[str] = Form(None, description="上传到的目录路径（相对路径）"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    files: List[UploadFile] = File(...),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
            if not filename or "/" in filename or ".." in filename:
                continue

            file_path = target_dir / filename

            # 保存文件
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            uploaded_files.append(
                {
                    "filename": filename,
                    "path": str(file_path.relative_to(root_dir)),
                    "size": len(content),
                }
            )

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
                    "root_only": root_only,
                },
                ip_address=get_client_ip(request),
            )

        return {
            "success": True,
            "message": f"成功上传 {len(uploaded_files)} 个文件",
            "files": uploaded_files,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传文件失败: {str(e)}",
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
    db: Session = Depends(get_db),
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
                status_code=status.HTTP_400_BAD_REQUEST, detail="未选择文件"
            )

        # 验证文件格式
        filename_lower = file.filename.lower()
        if not any(
            filename_lower.endswith(ext) for ext in [".zip", ".tar.gz", ".tgz", ".tar"]
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar",
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
            if stem.endswith(".tar") and suffix == ".gz":
                # 处理 .tar.gz 的情况
                stem = stem[:-4]
                suffix = ".tar.gz"
            file_path = packages_dir / f"{stem}_{timestamp}{suffix}"

        # 保存文件
        content = await file.read()
        with open(file_path, "wb") as f:
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
                "size": len(content),
            },
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "资源包上传成功",
            "filename": file_path.name,
            "size": len(content),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传资源包失败: {str(e)}",
        )


@router.get("/packages", summary="列出已上传的静态资源包")
async def list_packages(current_user: User = Depends(get_current_user)):
    """列出已上传的静态资源包"""
    try:
        packages_dir = get_packages_dir()

        if not packages_dir.exists():
            return {"success": True, "packages": []}

        packages = []
        for file_path in sorted(
            packages_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True
        ):
            if file_path.is_file():
                stat = file_path.stat()
                filename_lower = file_path.name.lower()
                is_valid = any(
                    filename_lower.endswith(ext)
                    for ext in [".zip", ".tar.gz", ".tgz", ".tar"]
                )
                if is_valid:
                    packages.append(
                        {
                            "filename": file_path.name,
                            "size": stat.st_size,
                            "uploaded_time": datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                        }
                    )

        return {"success": True, "packages": packages}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出资源包失败: {str(e)}",
        )


@router.delete("/packages/{filename}", summary="删除已上传的静态资源包")
async def delete_package(
    filename: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除已上传的静态资源包"""
    try:
        # 验证文件名，防止目录遍历
        if "/" in filename or ".." in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名"
            )

        packages_dir = get_packages_dir()
        file_path = packages_dir / filename

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="资源包不存在"
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
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "资源包已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除资源包失败: {str(e)}",
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
    db: Session = Depends(get_db),
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
                status_code=status.HTTP_400_BAD_REQUEST, detail="未选择文件"
            )

        filename_lower = file.filename.lower()
        if not (
            filename_lower.endswith(".zip")
            or filename_lower.endswith(".tar.gz")
            or filename_lower.endswith(".tgz")
            or filename_lower.endswith(".tar")
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar",
            )

        packages_dir = get_packages_dir()
        file_path = packages_dir / file.filename

        # 如果文件已存在，添加时间戳后缀
        if file_path.exists():
            import time

            name_parts = file.filename.rsplit(".", 1)
            if len(name_parts) == 2:
                file.filename = f"{name_parts[0]}_{int(time.time())}.{name_parts[1]}"
            else:
                file.filename = f"{file.filename}_{int(time.time())}"
            file_path = packages_dir / file.filename

        # 保存文件
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_upload",
            target=file.filename,
            details={"size": len(content)},
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": f"资源包上传成功: {file.filename}",
            "filename": file.filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传资源包失败: {str(e)}",
        )


@router.get("/packages", summary="列出已上传的静态资源包")
async def list_packages(current_user: User = Depends(get_current_user)):
    """列出所有已上传的静态资源包"""
    try:
        packages_dir = get_packages_dir()

        if not packages_dir.exists():
            return {"success": True, "packages": []}

        packages = []
        for file_path in packages_dir.iterdir():
            if file_path.is_file():
                filename_lower = file_path.name.lower()
                if (
                    filename_lower.endswith(".zip")
                    or filename_lower.endswith(".tar.gz")
                    or filename_lower.endswith(".tgz")
                    or filename_lower.endswith(".tar")
                ):
                    stat = file_path.stat()
                    packages.append(
                        PackageInfo(
                            filename=file_path.name,
                            size=stat.st_size,
                            uploaded_time=datetime.fromtimestamp(
                                stat.st_mtime
                            ).isoformat(),
                        )
                    )

        # 按上传时间倒序排序
        packages.sort(key=lambda x: x.uploaded_time, reverse=True)

        return {"success": True, "packages": [p.dict() for p in packages]}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"列出资源包失败: {str(e)}",
        )


@router.get("/packages/download/{filename}", summary="下载静态资源包")
async def download_package(
    filename: str, current_user: User = Depends(get_current_user_optional_query)
):
    """下载静态资源包（使用流式传输，支持大文件）。支持 Header 或查询参数传递 token。"""
    try:
        # 验证文件名，防止目录遍历攻击
        if "/" in filename or ".." in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名"
            )

        packages_dir = get_packages_dir()
        file_path = packages_dir / filename

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="资源包不存在"
            )

        # 确保文件在 packages 目录内
        try:
            file_path.resolve().relative_to(packages_dir.resolve())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径"
            )

        # 使用流式传输，支持大文件下载
        def iterfile():
            with open(file_path, mode="rb") as file_like:
                while True:
                    chunk = file_like.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(file_path.stat().st_size),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载资源包失败: {str(e)}",
        )


@router.delete("/packages/{filename}", summary="删除已上传的静态资源包")
async def delete_package(
    filename: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除已上传的静态资源包"""
    try:
        # 验证文件名，防止目录遍历攻击
        if "/" in filename or ".." in filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名"
            )

        packages_dir = get_packages_dir()
        file_path = packages_dir / filename

        if not file_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="资源包不存在"
            )

        # 确保文件在 packages 目录内
        try:
            file_path.resolve().relative_to(packages_dir.resolve())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径"
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
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "资源包已删除"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除资源包失败: {str(e)}",
        )


@router.post("/deploy-package", summary="部署静态资源包到 html 目录")
async def deploy_package(
    request: Request,
    filename: Optional[str] = Form(
        None, description="已上传的资源包文件名（如果提供则使用已上传的文件）"
    ),
    file: Optional[UploadFile] = File(
        None, description="新上传的文件（如果提供则使用新文件）"
    ),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    extract_to_subdir: bool = Form(False, description="是否解压到子目录（使用包名）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
            if "/" in filename or ".." in filename:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名"
                )
            packages_dir = get_packages_dir()
            package_path = packages_dir / filename
            if not package_path.exists():
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"资源包 {filename} 不存在",
                )
            tmp_path = package_path
            original_filename = filename
            # 读取文件内容用于日志记录
            with open(package_path, "rb") as f:
                content = f.read()
        elif file and file.filename:
            # 使用新上传的文件
            original_filename = file.filename
            # 保存上传的文件到临时目录
            import tempfile

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=Path(file.filename).suffix
            ) as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_path = Path(tmp_file.name)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请提供已上传的文件名或上传新文件",
            )

        try:
            # 获取 html 目录
            html_dir = get_version_root_dir(version, root_only=False)

            # 确定解压目标目录
            if extract_to_subdir:
                # 使用包名（不含扩展名）作为子目录名
                package_name = Path(original_filename).stem
                if package_name.endswith(".tar"):
                    package_name = package_name[:-4]
                target_dir = html_dir / package_name
            else:
                target_dir = html_dir

            # 确保目标目录存在
            target_dir.mkdir(parents=True, exist_ok=True)

            # 根据文件类型解压
            filename_lower = original_filename.lower()
            if filename_lower.endswith(".zip"):
                with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                    zip_ref.extractall(target_dir)
            elif filename_lower.endswith((".tar.gz", ".tgz")):
                with tarfile.open(tmp_path, "r:gz") as tar_ref:
                    tar_ref.extractall(target_dir)
            elif filename_lower.endswith(".tar"):
                with tarfile.open(tmp_path, "r") as tar_ref:
                    tar_ref.extractall(target_dir)
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar",
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
                    "from_uploaded": bool(filename),
                },
                ip_address=get_client_ip(request),
            )

            return {
                "success": True,
                "message": f"静态资源包已成功部署到 {target_dir.relative_to(html_dir)}",
                "target_dir": str(target_dir.relative_to(html_dir)),
            }
        finally:
            # 清理临时文件（仅当是新上传的文件时）
            if not filename and tmp_path.exists():
                tmp_path.unlink()

    except HTTPException:
        raise
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="ZIP 文件格式错误或已损坏"
        )
    except tarfile.TarError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TAR 文件格式错误: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"部署静态资源包失败: {str(e)}",
        )


@router.post("/extract-package", summary="从静态文件夹根目录提取资源包")
async def extract_package(
    request: Request,
    directory: Optional[str] = Form(None, description="Nginx 目录名称（版本号）"),
    delete_after_extract: bool = Form(
        False, description="提取后是否删除静态文件夹中的资源包"
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    从静态文件夹根目录（html目录）扫描并提取资源包文件

    扫描html目录中的压缩包文件（.zip、.tar.gz、.tgz、.tar），
    将它们复制到资源包存储目录。

    如果 delete_after_extract 为 True，提取后会删除 html 目录中的这些压缩包文件
    """
    try:
        # directory 就是版本号，使用它来获取 html 目录
        version = directory
        # 获取 html 目录
        html_dir = get_version_root_dir(version, root_only=False)

        if not html_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="html 目录不存在"
            )

        # 扫描html目录中的压缩包文件
        package_extensions = [".zip", ".tar.gz", ".tgz", ".tar"]
        found_packages = []

        for item in html_dir.iterdir():
            if item.is_file():
                filename_lower = item.name.lower()
                # 检查是否是压缩包文件
                if any(filename_lower.endswith(ext) for ext in package_extensions):
                    found_packages.append(item)

        if not found_packages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="html 目录中未找到任何资源包文件（.zip、.tar.gz、.tgz、.tar）",
            )

        # 获取资源包存储目录
        packages_dir = get_packages_dir()

        extracted_packages = []
        total_size = 0

        for package_file in found_packages:
            filename = package_file.name

            # 目标路径
            target_path = packages_dir / filename

            # 如果同名文件已存在，添加时间戳
            if target_path.exists():
                from datetime import datetime

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                stem = package_file.stem
                suffix = package_file.suffix
                # 处理 .tar.gz 的情况
                if stem.endswith(".tar") and suffix == ".gz":
                    stem = stem[:-4]
                    suffix = ".tar.gz"
                filename = f"{stem}_{timestamp}{suffix}"
                target_path = packages_dir / filename

            # 复制文件到资源包目录
            shutil.copy2(package_file, target_path)
            package_size = target_path.stat().st_size
            total_size += package_size

            extracted_packages.append(
                {
                    "original_name": package_file.name,
                    "saved_as": filename,
                    "size": package_size,
                }
            )

            # 如果选择删除，删除html目录中的压缩包文件
            if delete_after_extract:
                package_file.unlink()

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="package_extract",
            target=f"{len(extracted_packages)}个资源包",
            details={
                "extracted_count": len(extracted_packages),
                "total_size": total_size,
                "version": version,
                "delete_after_extract": delete_after_extract,
                "packages": [p["saved_as"] for p in extracted_packages],
            },
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": f"成功提取 {len(extracted_packages)} 个资源包{'，已删除源文件' if delete_after_extract else ''}",
            "extracted_count": len(extracted_packages),
            "total_size": total_size,
            "packages": extracted_packages,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"提取资源包失败: {str(e)}",
        )


@router.put("/{file_path:path}", summary="修改文件内容")
async def update_file(
    file_path: str,
    request: Request,
    content: str = Form(...),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改文件内容"""
    try:
        target_path = validate_path(file_path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
            )

        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径是目录，不是文件",
            )

        # 保存文件内容
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="file_update",
            target=file_path,
            details={"size": len(content), "version": version, "root_only": root_only},
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "文件已更新"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新文件失败: {str(e)}",
        )


@router.delete("/{file_path:path}", summary="删除文件或目录")
async def delete_file(
    file_path: str,
    request: Request,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除文件或目录"""
    try:
        target_path = validate_path(file_path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件或目录不存在"
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
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除失败: {str(e)}",
        )


@router.post("/mkdir", summary="创建目录")
async def create_directory(
    request: Request,
    path: Optional[str] = Form(None, description="父目录路径（相对路径）"),
    name: str = Form(..., description="目录名称"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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
                status_code=status.HTTP_400_BAD_REQUEST, detail="目录已存在"
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
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "目录创建成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建目录失败: {str(e)}",
        )


@router.post("/rename/{file_path:path}", summary="重命名文件或目录")
async def rename_file(
    file_path: str,
    request: Request,
    new_name: str = Form(...),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重命名文件或目录"""
    try:
        root_dir = get_version_root_dir(version, root_only)
        target_path = validate_path(file_path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件或目录不存在"
            )

        # 验证新名称
        if "/" in new_name or ".." in new_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件名"
            )

        new_path = target_path.parent / new_name

        # 验证新路径
        relative_path = str(new_path.relative_to(root_dir))
        validate_path(relative_path, version, root_only)

        if new_path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="目标文件名已存在"
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
            ip_address=get_client_ip(request),
        )

        return {"success": True, "message": "重命名成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"重命名失败: {str(e)}",
        )


@router.get("/download/{file_path:path}", summary="下载文件")
async def download_file(
    file_path: str,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    root_only: bool = Query(False, description="是否管理整个安装目录(而非仅 html)"),
    current_user: User = Depends(get_current_user_optional_query),
):
    """下载文件（使用流式传输，支持大文件）。支持 Header 或查询参数传递 token。"""
    try:
        target_path = validate_path(file_path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
            )

        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="无法下载目录"
            )

        # 使用流式传输，支持大文件下载
        def iterfile():
            with open(target_path, mode="rb") as file_like:
                while True:
                    chunk = file_like.read(1024 * 1024)  # 1MB chunks
                    if not chunk:
                        break
                    yield chunk

        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{target_path.name}"',
                "Content-Length": str(target_path.stat().st_size),
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下载文件失败: {str(e)}",
        )


@router.get("/{file_path:path}", summary="获取文件内容")
async def get_file(
    file_path: str,
    version: Optional[str] = Query(None, description="Nginx 版本号"),
    root_only: bool = Query(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
):
    """获取文件内容"""
    try:
        target_path = validate_path(file_path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在"
            )

        if target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径是目录，不是文件",
            )

        with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        return {"success": True, "content": content, "path": file_path}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取文件失败: {str(e)}",
        )


@router.post("/compress", summary="压缩文件夹")
async def compress_directory(
    request: Request,
    path: str = Form(..., description="要压缩的文件夹路径（相对路径）"),
    format: str = Form("zip", description="压缩格式：zip 或 tar.gz"),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    压缩指定文件夹

    支持的格式：
    - zip
    - tar.gz
    """
    try:
        # 验证格式
        format = format.lower()
        if format not in ["zip", "tar.gz", "tgz"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的压缩格式，仅支持 zip、tar.gz、tgz",
            )

        root_dir = get_version_root_dir(version, root_only)
        target_path = validate_path(path, version, root_only)

        if not target_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文件夹不存在"
            )

        if not target_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="指定路径不是文件夹"
            )

        # 检查目录是否为空
        items = list(target_path.iterdir())
        if not items:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="文件夹为空，无法压缩"
            )

        # 生成压缩包名称（使用文件夹名称）
        folder_name = target_path.name
        if format == "zip":
            ext = ".zip"
        elif format in ["tar.gz", "tgz"]:
            ext = ".tar.gz"
        else:
            ext = ".zip"

        # 压缩包保存在同一目录下
        archive_name = f"{folder_name}{ext}"
        archive_path = target_path.parent / archive_name

        # 如果同名文件已存在，添加时间戳
        if archive_path.exists():
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"{folder_name}_{timestamp}{ext}"
            archive_path = target_path.parent / archive_name

        # 创建压缩包
        try:
            if format == "zip":
                with zipfile.ZipFile(
                    archive_path, "w", zipfile.ZIP_DEFLATED
                ) as zip_ref:
                    # 遍历文件夹中的所有文件和目录
                    for item in target_path.rglob("*"):
                        if item.is_file():
                            # 计算相对路径（相对于要压缩的文件夹）
                            arcname = item.relative_to(target_path)
                            zip_ref.write(item, arcname)
            else:  # tar.gz
                with tarfile.open(archive_path, "w:gz") as tar_ref:
                    # 遍历文件夹中的所有文件和目录
                    for item in target_path.rglob("*"):
                        if item.is_file():
                            # 计算相对路径（相对于要压缩的文件夹）
                            arcname = item.relative_to(target_path)
                            tar_ref.add(item, arcname=arcname)

            archive_size = archive_path.stat().st_size
            relative_archive_path = str(archive_path.relative_to(root_dir))

            # 记录操作日志
            create_audit_log(
                db=db,
                user_id=current_user.id,
                username=current_user.username,
                action="dir_compress",
                target=path,
                details={
                    "archive_path": relative_archive_path,
                    "archive_name": archive_name,
                    "size": archive_size,
                    "format": format,
                    "version": version,
                    "root_only": root_only,
                },
                ip_address=get_client_ip(request),
            )

            return {
                "success": True,
                "message": "文件夹压缩成功",
                "archive_path": relative_archive_path,
                "archive_name": archive_name,
                "size": archive_size,
            }
        except Exception as e:
            # 如果压缩失败，删除已创建的文件
            if archive_path.exists():
                archive_path.unlink()
            raise e

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"压缩文件夹失败: {str(e)}",
        )


@router.post("/extract", summary="解压压缩包到指定目录")
async def extract_archive(
    request: Request,
    path: str = Form(..., description="压缩包文件路径（相对路径）"),
    extract_to: Optional[str] = Form(
        None, description="解压目标目录（相对路径，默认为压缩包所在目录）"
    ),
    version: Optional[str] = Form(None, description="Nginx 版本号"),
    root_only: bool = Form(False, description="是否管理整个安装目录（而非仅 html）"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    解压压缩包到指定目录

    支持的格式：
    - .zip
    - .tar.gz / .tgz
    - .tar
    """
    try:
        root_dir = get_version_root_dir(version, root_only)
        archive_path = validate_path(path, version, root_only)

        if not archive_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="压缩包不存在"
            )

        if archive_path.is_dir():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="指定路径是文件夹，不是压缩包",
            )

        # 验证文件格式
        filename_lower = archive_path.name.lower()
        is_zip = filename_lower.endswith(".zip")
        is_tar_gz = filename_lower.endswith((".tar.gz", ".tgz"))
        is_tar = filename_lower.endswith(".tar")

        if not (is_zip or is_tar_gz or is_tar):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不支持的文件格式，仅支持 .zip, .tar.gz, .tgz, .tar",
            )

        # 确定解压目标目录
        if extract_to:
            target_dir = validate_path(extract_to, version, root_only)
        else:
            # 默认解压到压缩包所在目录
            target_dir = archive_path.parent

        # 确保目标目录存在
        target_dir.mkdir(parents=True, exist_ok=True)

        # 解压文件
        extracted_files = []
        try:
            if is_zip:
                with zipfile.ZipFile(archive_path, "r") as zip_ref:
                    zip_ref.extractall(target_dir)
                    extracted_files = zip_ref.namelist()
            elif is_tar_gz:
                with tarfile.open(archive_path, "r:gz") as tar_ref:
                    tar_ref.extractall(target_dir)
                    extracted_files = tar_ref.getnames()
            elif is_tar:
                with tarfile.open(archive_path, "r") as tar_ref:
                    tar_ref.extractall(target_dir)
                    extracted_files = tar_ref.getnames()

            relative_target_dir = str(target_dir.relative_to(root_dir))

            # 记录操作日志
            create_audit_log(
                db=db,
                user_id=current_user.id,
                username=current_user.username,
                action="archive_extract",
                target=path,
                details={
                    "extract_to": relative_target_dir,
                    "extracted_files_count": len(extracted_files),
                    "version": version,
                    "root_only": root_only,
                },
                ip_address=get_client_ip(request),
            )

            return {
                "success": True,
                "message": f"压缩包解压成功，共解压 {len(extracted_files)} 个文件/目录",
                "extract_to": relative_target_dir,
                "extracted_files_count": len(extracted_files),
            }
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ZIP 文件格式错误或已损坏",
            )
        except tarfile.TarError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"TAR 文件格式错误: {str(e)}",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解压压缩包失败: {str(e)}",
        )
