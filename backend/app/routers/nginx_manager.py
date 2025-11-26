"""
Nginx 多版本管理路由
"""
import os
import tarfile
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    Request,
    UploadFile,
    File,
    Form,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, User
from app.config import get_config
from app.database import get_db
from app.utils.audit import create_audit_log, get_client_ip


router = APIRouter(prefix="/api/nginx", tags=["nginx"])


class NginxVersionInfo(BaseModel):
    """Nginx 版本信息"""

    version: str
    install_path: str
    executable: str
    running: bool
    pid: Optional[int] = None
    source: Optional[str] = None  # download / upload / prebuilt
    error: Optional[str] = None


class NginxDownloadRequest(BaseModel):
    """在线下载并编译 Nginx 请求"""

    version: str
    url: Optional[str] = None


class NginxBuildResult(BaseModel):
    """编译结果"""

    success: bool
    message: str
    version: str
    build_log_path: Optional[str] = None


def _get_versions_root() -> Path:
    """获取 Nginx 多版本安装根目录"""
    config = get_config()
    return Path(config.nginx.versions_root)


def _get_install_path(version: str) -> Path:
    """根据版本号获取安装路径"""
    return _get_versions_root() / version


def _get_nginx_executable(install_path: Path) -> Path:
    """
    获取指定安装路径下的 Nginx 可执行文件

    约定：编译时使用 --prefix=<install_path>，则可执行文件位于 <install_path>/sbin/nginx
    """
    return install_path / "sbin" / "nginx"


def _get_pid_file(install_path: Path) -> Path:
    """
    获取 PID 文件路径

    约定：使用默认前缀时，PID 文件位于 <install_path>/logs/nginx.pid
    """
    return install_path / "logs" / "nginx.pid"


def _get_build_root() -> Path:
    """获取源码构建根目录"""
    config = get_config()
    return Path(config.nginx.build_root)


def _get_build_logs_dir() -> Path:
    """获取编译日志目录"""
    config = get_config()
    return Path(config.nginx.build_logs_dir)


def _ensure_nginx_dirs() -> None:
    """确保多版本相关目录存在"""
    _get_versions_root().mkdir(parents=True, exist_ok=True)
    _get_build_root().mkdir(parents=True, exist_ok=True)
    _get_build_logs_dir().mkdir(parents=True, exist_ok=True)


def _check_process_running(pid: int) -> bool:
    """检查指定 PID 的进程是否仍在运行"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_build_log_path(version: str) -> Path:
    """获取编译日志文件路径"""
    return _get_build_logs_dir() / f"{version}.log"


def _write_build_log(version: str, content: str) -> Path:
    """写入编译日志"""
    log_path = _get_build_log_path(version)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(content, encoding="utf-8", errors="ignore")
    return log_path


def _detect_source_dir(build_dir: Path) -> Path:
    """在解压后的构建目录中检测源码根目录"""
    subdirs = [p for p in build_dir.iterdir() if p.is_dir()]
    if not subdirs:
        raise RuntimeError("在源码包中未找到有效的目录")
    # 通常 nginx-<version> 就一个目录，取第一个
    return subdirs[0]


def _compile_nginx_from_source(source_tar: Path, version: str) -> NginxBuildResult:
    """
    从源码编译安装 Nginx

    Args:
        source_tar: 源码 tar.gz 文件路径
        version: 目标版本号
    """
    _ensure_nginx_dirs()
    build_root = _get_build_root()
    install_path = _get_install_path(version)
    build_dir = build_root / version

    # 如果目标版本已经存在，避免覆盖
    if install_path.exists() and any(install_path.iterdir()):
        msg = f"Nginx 版本 {version} 已存在，请先删除或选择其他版本号"
        log_path = _write_build_log(version, msg)
        return NginxBuildResult(
            success=False,
            message=msg,
            version=version,
            build_log_path=str(log_path),
        )

    # 清理并创建构建目录
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    logs: list[str] = []

    try:
        logs.append(f"使用源码包: {source_tar}")

        # 解压源码
        if not source_tar.exists():
            raise RuntimeError(f"源码包不存在: {source_tar}")

        with tarfile.open(source_tar, "r:gz") as tar:
            tar.extractall(build_dir)
        logs.append(f"已解压到构建目录: {build_dir}")

        source_dir = _detect_source_dir(build_dir)
        logs.append(f"检测到源码目录: {source_dir}")

        install_path.mkdir(parents=True, exist_ok=True)
        logs.append(f"目标安装路径: {install_path}")

        # configure
        configure_cmd = [
            "./configure",
            f"--prefix={install_path}",
        ]
        logs.append(f"执行配置命令: {' '.join(configure_cmd)}")
        result = subprocess.run(
            configure_cmd,
            cwd=source_dir,
            capture_output=True,
            text=True,
        )
        logs.append(result.stdout)
        logs.append(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("configure 失败")

        # make
        make_cmd = ["make", "-j", str(os.cpu_count() or 1)]
        logs.append(f"执行编译命令: {' '.join(make_cmd)}")
        result = subprocess.run(
            make_cmd,
            cwd=source_dir,
            capture_output=True,
            text=True,
        )
        logs.append(result.stdout)
        logs.append(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("make 失败")

        # make install
        install_cmd = ["make", "install"]
        logs.append(f"执行安装命令: {' '.join(install_cmd)}")
        result = subprocess.run(
            install_cmd,
            cwd=source_dir,
            capture_output=True,
            text=True,
        )
        logs.append(result.stdout)
        logs.append(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("make install 失败")

        # 校验可执行文件
        executable = _get_nginx_executable(install_path)
        if not executable.exists():
            raise RuntimeError(f"安装完成但未找到可执行文件: {executable}")

        full_log = "\n".join(logs)
        log_path = _write_build_log(version, full_log)
        return NginxBuildResult(
            success=True,
            message=f"Nginx {version} 编译安装成功",
            version=version,
            build_log_path=str(log_path),
        )
    except Exception as e:
        logs.append(f"编译过程出错: {e}")
        full_log = "\n".join(logs)
        log_path = _write_build_log(version, full_log)
        return NginxBuildResult(
            success=False,
            message=f"编译安装失败: {e}",
            version=version,
            build_log_path=str(log_path),
        )


def _get_version_status(version: str) -> NginxVersionInfo:
    """获取单个版本的状态信息"""
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)

    if not install_path.exists():
        return NginxVersionInfo(
            version=version,
            install_path=str(install_path),
            executable=str(executable),
            running=False,
            error="install_path_not_found",
        )

    if not executable.exists():
        return NginxVersionInfo(
            version=version,
            install_path=str(install_path),
            executable=str(executable),
            running=False,
            error="executable_not_found",
        )

    pid_file = _get_pid_file(install_path)
    pid: Optional[int] = None
    running = False

    if pid_file.exists():
        try:
            content = pid_file.read_text(encoding="utf-8").strip()
            if content:
                pid = int(content)
                running = _check_process_running(pid)
        except Exception:
            pid = None
            running = False

    return NginxVersionInfo(
        version=version,
        install_path=str(install_path),
        executable=str(executable),
        running=running,
        pid=pid,
    )


def _list_installed_versions() -> List[NginxVersionInfo]:
    """扫描安装目录，获取所有已安装版本信息"""
    versions_root = _get_versions_root()
    if not versions_root.exists():
        return []

    items: List[NginxVersionInfo] = []
    for child in versions_root.iterdir():
        if child.is_dir():
            items.append(_get_version_status(child.name))
    return items


def _download_to_file(url: str, dest: Path) -> None:
    """将远程 URL 内容下载到本地文件（简单实现，避免额外依赖）"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as resp, open(dest, "wb") as f:
        shutil.copyfileobj(resp, f)


def _infer_version_from_filename(filename: str) -> Optional[str]:
    """
    从 nginx 源码包文件名中推断版本号
    例如: nginx-1.28.0.tar.gz -> 1.28.0
    """
    name = filename
    if name.endswith(".tar.gz"):
        name = name[:-7]
    elif name.endswith(".tgz"):
        name = name[:-4]
    if name.startswith("nginx-"):
        return name[len("nginx-") :]
    return None


@router.get("/versions", response_model=List[NginxVersionInfo], summary="获取已安装的 Nginx 版本列表")
async def list_nginx_versions(
    current_user: User = Depends(get_current_user),
) -> List[NginxVersionInfo]:
    """
    获取当前容器内已安装的 Nginx 版本列表及其运行状态。

    仅扫描配置中约定的 versions_root 目录。
    """
    return _list_installed_versions()


@router.post(
    "/versions/download",
    response_model=NginxBuildResult,
    summary="在线下载并编译指定版本 Nginx",
)
async def download_and_build_nginx_version(
    payload: NginxDownloadRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NginxBuildResult:
    """
    在线下载指定版本的 Nginx 源码包并在容器内编译安装。

    - 默认使用官方下载地址: https://nginx.org/download/nginx-<version>.tar.gz
    - 也可以通过 url 字段指定自定义下载地址
    """
    version = payload.version.strip()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="版本号不能为空",
        )

    _ensure_nginx_dirs()
    build_root = _get_build_root()

    # 构造默认下载地址
    if payload.url:
        url = payload.url
    else:
        url = f"https://nginx.org/download/nginx-{version}.tar.gz"

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError("无效的下载地址")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"下载地址不合法: {e}",
        )

    source_tar = build_root / f"nginx-{version}.tar.gz"
    try:
        _download_to_file(url, source_tar)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"下载源码包失败: {e}",
        )

    result = _compile_nginx_from_source(source_tar, version)

    # 记录审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_build_download",
        target=version,
        details={
            "url": url,
            "success": result.success,
            "build_log_path": result.build_log_path,
        },
        ip_address=get_client_ip(request),
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message,
        )

    return result


@router.post(
    "/versions/upload",
    response_model=NginxBuildResult,
    summary="上传源码包并编译 Nginx",
)
async def upload_and_build_nginx_version(
    request: Request,
    file: UploadFile = File(...),
    version: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NginxBuildResult:
    """
    上传本地 Nginx 源码包并在容器内编译安装。

    - 支持无网络环境下的安装
    - version 为空时会尝试从文件名中推断（例如 nginx-1.28.0.tar.gz）
    """
    filename = file.filename or ""
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="上传文件名不能为空",
        )

    if not (filename.endswith(".tar.gz") or filename.endswith(".tgz")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .tar.gz 或 .tgz 格式的源码包",
        )

    inferred_version = _infer_version_from_filename(filename)
    version = (version or inferred_version or "").strip()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无法从文件名推断版本号，请手动提供 version",
        )

    _ensure_nginx_dirs()
    build_root = _get_build_root()
    dest = build_root / filename

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"保存上传文件失败: {e}",
        )

    result = _compile_nginx_from_source(dest, version)

    # 记录审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_build_upload",
        target=version,
        details={
            "filename": filename,
            "success": result.success,
            "build_log_path": result.build_log_path,
        },
        ip_address=get_client_ip(request),
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message,
        )

    return result


@router.get(
    "/versions/{version}/build_log",
    summary="获取指定版本的编译日志",
)
async def get_nginx_build_log(
    version: str,
    current_user: User = Depends(get_current_user),
):
    """返回指定版本的编译日志内容"""
    log_path = _get_build_log_path(version)
    if not log_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="编译日志不存在",
        )
    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取编译日志失败: {e}",
        )

    return {
        "version": version,
        "build_log_path": str(log_path),
        "content": content[-20000:],  # 截取最后 2 万字符，避免过大
    }


@router.get(
    "/versions/{version}/status",
    response_model=NginxVersionInfo,
    summary="获取指定版本 Nginx 运行状态",
)
async def get_nginx_version_status(
    version: str,
    current_user: User = Depends(get_current_user),
) -> NginxVersionInfo:
    """获取指定版本 Nginx 的安装与运行状态"""
    info = _get_version_status(version)
    if info.error == "install_path_not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本未安装: {version}",
        )
    return info


@router.post(
    "/versions/{version}/start",
    summary="启动指定版本的 Nginx",
)
async def start_nginx_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    启动指定版本的 Nginx。

    约定：
    - 可执行文件位于 <versions_root>/<version>/sbin/nginx
    - 使用全局配置中的 nginx.conf（/etc/nginx/nginx.conf），前缀为该版本的安装路径
    """
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)
    config = get_config()

    if not install_path.exists() or not executable.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本未正确安装: {version}",
        )

    # 如果已经在运行，则直接返回
    current_info = _get_version_status(version)
    if current_info.running:
        return {
            "success": True,
            "message": f"Nginx 版本 {version} 已在运行",
            "version": current_info,
        }

    # 确保必要目录存在（logs、conf 等）
    (install_path / "logs").mkdir(parents=True, exist_ok=True)

    # 先测试配置
    try:
        import subprocess

        test_cmd = [
            str(executable),
            "-t",
            "-c",
            config.nginx.config_path,
            "-p",
            str(install_path),
        ]
        test_result = subprocess.run(
            test_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if test_result.returncode != 0:
            output = test_result.stdout + test_result.stderr
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"配置测试失败: {output}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"配置测试出错: {str(e)}",
        )

    # 启动 Nginx（作为守护进程，由其自己在后台运行）
    try:
        import subprocess

        cmd = [
            str(executable),
            "-c",
            config.nginx.config_path,
            "-p",
            str(install_path),
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            output = result.stdout + result.stderr
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Nginx 启动失败: {output}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nginx 启动出错: {str(e)}",
        )

    # 写入审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_start",
        target=version,
        details={"install_path": str(install_path)},
        ip_address=get_client_ip(request),
    )

    info = _get_version_status(version)
    return {
        "success": True,
        "message": f"Nginx 版本 {version} 启动成功",
        "version": info,
    }


@router.post(
    "/versions/{version}/stop",
    summary="停止指定版本的 Nginx",
)
async def stop_nginx_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    停止指定版本的 Nginx。

    约定：
    - 可执行文件位于 <versions_root>/<version>/sbin/nginx
    - 使用全局配置中的 nginx.conf 和该版本安装路径作为前缀
    """
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)
    config = get_config()

    if not install_path.exists() or not executable.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本未正确安装: {version}",
        )

    current_info = _get_version_status(version)
    if not current_info.running:
        return {
            "success": True,
            "message": f"Nginx 版本 {version} 已经停止",
            "version": current_info,
        }

    try:
        import subprocess

        cmd = [
            str(executable),
            "-c",
            config.nginx.config_path,
            "-p",
            str(install_path),
            "-s",
            "quit",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            output = result.stdout + result.stderr
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Nginx 停止失败: {output}",
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Nginx 停止出错: {str(e)}",
        )

    # 写入审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_stop",
        target=version,
        details={"install_path": str(install_path)},
        ip_address=get_client_ip(request),
    )

    info = _get_version_status(version)
    return {
        "success": True,
        "message": f"Nginx 版本 {version} 已停止",
        "version": info,
    }


