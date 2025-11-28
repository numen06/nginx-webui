"""
Nginx 多版本管理路由
"""

import os
import tarfile
import shutil
import subprocess
import signal
import time
import ssl
import threading
from pathlib import Path
from typing import List, Optional, Dict, Callable
from urllib.parse import urlparse
from urllib.request import urlopen, build_opener, HTTPHandler, HTTPSHandler
from urllib.request import Request as URLRequest
from urllib.error import HTTPError, URLError

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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user, User
from app.config import get_config
from app.database import get_db
from app.utils.audit import create_audit_log, get_client_ip


router = APIRouter(prefix="/api/nginx", tags=["nginx"])

# 下载进度存储（线程安全）
_download_progress: Dict[str, Dict] = {}
_progress_lock = threading.Lock()


class NginxVersionInfo(BaseModel):
    """Nginx 版本信息"""

    version: str
    install_path: str
    executable: str
    running: bool
    pid: Optional[int] = None
    source: Optional[str] = None  # download / upload / prebuilt
    error: Optional[str] = None
    # 是否已成功编译（即在 versions_root 下存在完整安装目录且包含 sbin/nginx）
    compiled: bool = False
    # 是否已准备好源码包（build_root 中存在对应 tar.gz / tgz）
    has_source: bool = False


class NginxDownloadRequest(BaseModel):
    """在线下载 Nginx 源码包请求（仅下载，不编译）"""

    version: str
    url: Optional[str] = None


class NginxBuildResult(BaseModel):
    """编译结果"""

    success: bool
    message: str
    version: str
    build_log_path: Optional[str] = None


class UrlCheckRequest(BaseModel):
    """URL 检查请求"""

    url: str


class UrlCheckResult(BaseModel):
    """URL 检查结果"""

    accessible: bool
    content_length: Optional[int] = None
    status_code: Optional[int] = None
    error: Optional[str] = None


class DownloadProgress(BaseModel):
    """下载进度"""

    status: str
    downloaded: int
    total: Optional[int] = None
    percentage: int
    error: Optional[str] = None


def _get_versions_root() -> Path:
    """获取 Nginx 多版本安装根目录"""
    config = get_config()
    raw = Path(config.nginx.versions_root)
    if raw.is_absolute():
        return raw
    # 当前文件在 backend/app/routers/nginx_manager.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


def _get_versions_root_raw() -> Path:
    """
    获取配置中原始的 versions_root 路径（不做绝对化），用于对外展示相对路径。
    """
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
    raw = Path(config.nginx.build_root)
    if raw.is_absolute():
        return raw
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


def _get_build_logs_dir() -> Path:
    """获取编译日志目录"""
    config = get_config()
    raw = Path(config.nginx.build_logs_dir)
    if raw.is_absolute():
        return raw
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


def _get_source_tar_path(version: str) -> Path:
    """根据版本号获取源码包 tar.gz 路径"""
    return _get_build_root() / f"nginx-{version}.tar.gz"


def _ensure_nginx_dirs() -> None:
    """确保多版本相关目录存在"""
    _get_versions_root().mkdir(parents=True, exist_ok=True)
    _get_build_root().mkdir(parents=True, exist_ok=True)
    _get_build_logs_dir().mkdir(parents=True, exist_ok=True)


def _get_nginx_config_path() -> Path:
    """
    获取 Nginx 配置文件的绝对路径

    - 如果配置中是绝对路径，则直接返回
    - 如果是相对路径，则相对于 backend 目录解析
    """
    config = get_config()
    raw = Path(config.nginx.config_path)
    if raw.is_absolute():
        return raw

    # 当前文件在 backend/app/routers/nginx_manager.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


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


def _kill_pids(pids: List[int]) -> dict:
    """
    尝试终止一批 PID：
    - 先发送 SIGTERM，短暂等待
    - 仍存活则发送 SIGKILL
    返回每个 PID 的处理结果
    """
    results: dict[int, dict] = {}

    for pid in pids:
        info = {"pid": pid, "term_sent": False, "kill_sent": False, "errors": []}
        try:
            os.kill(pid, signal.SIGTERM)
            info["term_sent"] = True
        except ProcessLookupError:
            # 进程已不存在
            results[pid] = info
            continue
        except Exception as e:
            info["errors"].append(f"SIGTERM 失败: {e}")

        time.sleep(0.2)
        if _check_process_running(pid):
            try:
                os.kill(pid, signal.SIGKILL)
                info["kill_sent"] = True
            except ProcessLookupError:
                pass
            except Exception as e:
                info["errors"].append(f"SIGKILL 失败: {e}")

        results[pid] = info

    return results


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


def _update_nginx_config_for_unified_dirs(install_path: Path, version: str) -> None:
    """
    更新编译后的nginx.conf，使其使用统一的配置目录和静态文件目录
    
    这样所有版本共享同一个配置目录（conf.d）和静态文件目录（html），
    在版本切换时配置和静态文件保持一致。
    """
    config = get_config()
    nginx_conf_path = install_path / "conf" / "nginx.conf"
    
    if not nginx_conf_path.exists():
        return
    
    # 解析配置路径（统一配置目录）
    conf_dir = Path(config.nginx.conf_dir)
    if not conf_dir.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        conf_dir = (backend_dir / conf_dir).resolve()
    
    # 解析静态文件目录路径
    static_dir = Path(config.nginx.static_dir)
    if not static_dir.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        static_dir = (backend_dir / static_dir).resolve()
    
    # 解析日志目录路径
    log_dir = Path(config.nginx.log_dir)
    if not log_dir.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        log_dir = (backend_dir / log_dir).resolve()
    
    access_log = Path(config.nginx.access_log)
    if not access_log.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        access_log = (backend_dir / access_log).resolve()
    
    error_log = Path(config.nginx.error_log)
    if not error_log.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        error_log = (backend_dir / error_log).resolve()
    
    # 确保目录存在
    conf_dir.mkdir(parents=True, exist_ok=True)
    static_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取原始配置
    original_content = nginx_conf_path.read_text(encoding="utf-8")
    
    # 生成新的配置内容
    # 保留基本的worker_processes、events等配置
    # 但修改http块中的配置，使其指向统一的目录
    new_config = f"""#user  nobody;
worker_processes  auto;

#error_log  logs/error.log;
#error_log  logs/error.log  notice;
#error_log  logs/error.log  info;

pid        logs/nginx.pid;

events {{
    worker_connections  1024;
}}

http {{
    include       mime.types;
    default_type  application/octet-stream;

    #log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
    #                  '$status $body_bytes_sent "$http_referer" '
    #                  '"$http_user_agent" "$http_x_forwarded_for"';

    access_log  {access_log};
    error_log   {error_log};

    sendfile        on;
    #tcp_nopush     on;

    #keepalive_timeout  0;
    keepalive_timeout  65;

    gzip  on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    # 使用统一的配置目录（所有版本共享）
    include {conf_dir}/*.conf;
}}
"""
    
    # 写入新配置
    nginx_conf_path.write_text(new_config, encoding="utf-8")


def _compile_nginx_from_source(source_tar: Path, version: str) -> NginxBuildResult:
    """
    从源码编译安装 Nginx

    Args:
        source_tar: 源码 tar.gz 文件路径
        version: 目标版本号
    """
    _ensure_nginx_dirs()
    build_root = _get_build_root()
    install_path = _get_install_path(
        version
    )  # 最终对外暴露的安装目录：<versions_root>/<version>
    build_dir = build_root / version  # 源码解压与编译目录：<build_root>/<version>
    tmp_install_path = build_root / f"{version}_install_tmp"  # 编译安装使用的临时目录

    # 如果目标版本已经存在，避免静默覆盖
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

    # 确保临时安装目录干净
    if tmp_install_path.exists():
        shutil.rmtree(tmp_install_path, ignore_errors=True)

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

        logs.append(f"临时安装路径: {tmp_install_path}")

        # configure
        configure_cmd = [
            "./configure",
            f"--prefix={tmp_install_path}",
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

        # 校验临时安装目录中的可执行文件
        executable = _get_nginx_executable(tmp_install_path)
        if not executable.exists():
            raise RuntimeError(f"安装完成但未找到可执行文件: {executable}")

        # 将临时安装目录整体移动到最终 versions_root 下
        if install_path.exists():
            shutil.rmtree(install_path, ignore_errors=True)
        install_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_install_path), str(install_path))
        logs.append(f"已将临时安装目录移动到正式路径: {install_path}")

        # 使用最终路径重新计算可执行文件路径，便于日志与后续校验
        executable = _get_nginx_executable(install_path)

        # 修改编译后的nginx.conf，使其使用统一的配置目录和静态文件目录
        _update_nginx_config_for_unified_dirs(install_path, version)
        logs.append("已更新nginx.conf以使用统一的配置目录和静态文件目录")

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
    # 内部使用绝对路径进行检测和编译
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)
    source_tar = _get_source_tar_path(version)

    # 对外返回时，安装路径使用相对于配置的 versions_root 的“原始路径”，避免在 API 中暴露绝对路径
    raw_root = _get_versions_root_raw()
    display_install_path = str(raw_root / version)
    display_executable = str(raw_root / version / "sbin" / "nginx")

    if not install_path.exists():
        return NginxVersionInfo(
            version=version,
            install_path=display_install_path,
            executable=display_executable,
            running=False,
            error=(
                "install_path_not_found" if not source_tar.exists() else "not_compiled"
            ),
            compiled=False,
            has_source=source_tar.exists(),
        )

    if not executable.exists():
        return NginxVersionInfo(
            version=version,
            install_path=display_install_path,
            executable=display_executable,
            running=False,
            error="executable_not_found",
            compiled=False,
            has_source=source_tar.exists(),
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
        install_path=display_install_path,
        executable=display_executable,
        running=running,
        pid=pid,
        compiled=executable.exists(),
        has_source=source_tar.exists(),
    )


def _list_all_versions() -> List[NginxVersionInfo]:
    """
    获取所有已知版本的信息：
    - 安装目录中的版本（已编译）
    - 仅存在源码包但尚未编译的版本（未编译）
    """
    versions: set[str] = set()

    versions_root = _get_versions_root()
    if versions_root.exists():
        for child in versions_root.iterdir():
            if child.is_dir():
                versions.add(child.name)

    build_root = _get_build_root()
    if build_root.exists():
        for p in build_root.iterdir():
            if p.is_file() and (p.name.endswith(".tar.gz") or p.name.endswith(".tgz")):
                v = _infer_version_from_filename(p.name)
                if v:
                    versions.add(v)

    items: List[NginxVersionInfo] = []
    for v in sorted(versions):
        items.append(_get_version_status(v))
    return items


def _check_url_accessible(url: str, timeout: int = 10) -> Dict[str, any]:
    """
    检查 URL 是否可以下载

    使用与下载函数相同的逻辑，只验证可访问性

    Returns:
        dict: {
            "accessible": bool,
            "content_length": int | None,
            "status_code": int | None,
            "error": str | None
        }
    """
    parsed = urlparse(url)

    # 基本 URL 验证
    if not parsed.scheme or not parsed.netloc:
        return {
            "accessible": False,
            "content_length": None,
            "status_code": None,
            "error": "无效的 URL 格式",
        }

    # 创建请求（与下载函数保持一致）
    req = URLRequest(url)
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; Nginx-WebUI/1.0)")

    try:
        # 使用与下载相同的 SSL 上下文处理
        if parsed.scheme == "https":
            context = ssl._create_unverified_context()
            resp = urlopen(req, context=context, timeout=timeout)
        else:
            resp = urlopen(req, timeout=timeout)

        # 读取响应头信息
        content_length = resp.headers.get("Content-Length")
        file_size = None
        if content_length:
            try:
                file_size = int(content_length)
            except:
                pass

        # 获取状态码
        status_code = getattr(resp, "code", None) or getattr(resp, "status", 200)

        # 读取少量数据验证连接
        resp.read(1024)
        resp.close()

        return {
            "accessible": True,
            "content_length": file_size,
            "status_code": status_code,
            "error": None,
        }

    except HTTPError as e:
        code = getattr(e, "code", None)
        reason = getattr(e, "reason", "") or ""
        return {
            "accessible": False,
            "content_length": None,
            "status_code": code,
            "error": (
                f"HTTP {code}: {reason}"
                if code
                else f"HTTP 错误: {reason}" if reason else "HTTP 错误"
            ),
        }
    except URLError as e:
        reason = getattr(e, "reason", "") or str(e)
        return {
            "accessible": False,
            "content_length": None,
            "status_code": None,
            "error": f"网络错误: {reason}",
        }
    except Exception as e:
        # 最简单的错误处理
        error_str = str(e) if e else "未知错误"
        return {
            "accessible": False,
            "content_length": None,
            "status_code": None,
            "error": f"检查失败: {error_str}",
        }


def _download_to_file(url: str, dest: Path, progress_key: Optional[str] = None) -> None:
    """
    将远程 URL 内容下载到本地文件，支持进度显示

    Args:
        url: 下载地址
        dest: 目标文件路径
        progress_key: 进度存储的键，用于查询下载进度
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)

    # 初始化进度
    if progress_key:
        with _progress_lock:
            _download_progress[progress_key] = {
                "status": "downloading",
                "downloaded": 0,
                "total": None,
                "percentage": 0,
                "error": None,
            }

    try:
        # 创建请求
        req = URLRequest(url)
        req.add_header("User-Agent", "Mozilla/5.0 (compatible; Nginx-WebUI/1.0)")

        # 某些环境（尤其是本地 macOS）可能缺少系统 CA，导致 HTTPS 校验证书失败。
        # 这里显式使用不校验证书的 SSL 上下文，保证下载功能可用。
        if parsed.scheme == "https":
            context = ssl._create_unverified_context()
            resp = urlopen(req, context=context, timeout=300)  # 5分钟超时
        else:
            resp = urlopen(req, timeout=300)  # 5分钟超时

        # 获取文件大小
        content_length = resp.headers.get("Content-Length")
        total_size = int(content_length) if content_length else None

        if progress_key:
            with _progress_lock:
                _download_progress[progress_key]["total"] = total_size

        # 下载文件并更新进度
        downloaded = 0
        chunk_size = 8192  # 8KB chunks

        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                # 更新进度
                if progress_key:
                    percentage = 0
                    if total_size:
                        percentage = min(100, int((downloaded / total_size) * 100))
                    elif downloaded > 0:
                        percentage = -1  # 未知大小，显示为进行中

                    with _progress_lock:
                        _download_progress[progress_key].update(
                            {
                                "downloaded": downloaded,
                                "total": total_size,
                                "percentage": percentage,
                            }
                        )

        # 标记完成
        if progress_key:
            with _progress_lock:
                _download_progress[progress_key].update(
                    {"status": "completed", "percentage": 100}
                )

    except Exception as e:
        # 标记错误
        if progress_key:
            with _progress_lock:
                _download_progress[progress_key].update(
                    {"status": "error", "error": str(e)}
                )
        raise


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


@router.get(
    "/versions",
    response_model=List[NginxVersionInfo],
    summary="获取已安装/已下载的 Nginx 版本列表",
)
async def list_nginx_versions(
    current_user: User = Depends(get_current_user),
) -> List[NginxVersionInfo]:
    """
    获取当前容器内已知的 Nginx 版本列表及其状态。

    数据来源：
    - versions_root 目录中的安装版本（已编译，可启动）
    - build_root 目录中的源码包（仅下载未编译）
    """
    return _list_all_versions()


@router.post(
    "/versions/download/check-url",
    response_model=UrlCheckResult,
    summary="检查下载地址是否可以访问",
)
async def check_download_url(
    payload: UrlCheckRequest,
    current_user: User = Depends(get_current_user),
) -> UrlCheckResult:
    """
    检查指定的下载地址是否可以访问

    用于在下载前验证 URL 是否有效
    """
    url = payload.url.strip()

    if not url:
        return UrlCheckResult(
            accessible=False,
            content_length=None,
            status_code=None,
            error="URL 不能为空",
        )

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return UrlCheckResult(
                accessible=False,
                content_length=None,
                status_code=None,
                error="无效的 URL 格式",
            )
    except Exception as e:
        return UrlCheckResult(
            accessible=False,
            content_length=None,
            status_code=None,
            error=f"URL 解析失败: {e}",
        )

    try:
        result = _check_url_accessible(url)

        # 确保 result 是字典类型
        if not isinstance(result, dict):
            return UrlCheckResult(
                accessible=False,
                content_length=None,
                status_code=None,
                error=f"检查函数返回了无效的数据类型: {type(result)}",
            )

        # 直接使用字典中的值，_check_url_accessible 已确保类型正确
        return UrlCheckResult(
            accessible=bool(result.get("accessible", False)),
            content_length=result.get("content_length"),
            status_code=result.get("status_code"),
            error=result.get("error"),
        )
    except Exception as e:
        # 捕获任何意外的异常，确保返回有效的 UrlCheckResult
        return UrlCheckResult(
            accessible=False,
            content_length=None,
            status_code=None,
            error=f"检查失败: {str(e)}",
        )


@router.get(
    "/versions/download/progress/{version}",
    response_model=DownloadProgress,
    summary="获取下载进度",
)
async def get_download_progress(
    version: str,
    current_user: User = Depends(get_current_user),
) -> DownloadProgress:
    """
    获取指定版本的下载进度
    """
    progress_key = f"download_{version}"
    with _progress_lock:
        progress = _download_progress.get(
            progress_key,
            {
                "status": "not_started",
                "downloaded": 0,
                "total": None,
                "percentage": 0,
                "error": None,
            },
        )
        # 返回 DownloadProgress 对象，确保格式一致
        return DownloadProgress(**progress)


@router.post(
    "/versions/download",
    response_model=NginxBuildResult,
    summary="在线下载指定版本 Nginx 源码包（不编译）",
)
async def download_and_build_nginx_version(
    payload: NginxDownloadRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NginxBuildResult:
    """
    在线下载指定版本的 Nginx 源码包。

    - 默认使用官方下载地址: https://nginx.org/download/nginx-<version>.tar.gz
    - 也可以通过 url 字段指定自定义下载地址

    仅负责下载并保存源码包，不进行编译。
    编译由 /versions/{version}/compile 接口触发。

    下载进度可通过 /versions/download/progress/{version} 接口查询。
    """
    version = payload.version.strip()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="版本号不能为空",
        )

    _ensure_nginx_dirs()

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

    # 检查 URL 是否可访问
    url_check = _check_url_accessible(url)

    # 确保 url_check 是字典类型
    if not isinstance(url_check, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"URL 检查返回了无效的数据类型",
        )

    # 安全地访问字典
    if not url_check.get("accessible", False):
        error_msg = url_check.get("error", "未知错误")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"下载地址不可访问: {error_msg}",
        )

    source_tar = _get_source_tar_path(version)
    progress_key = f"download_{version}"

    try:
        # 异步下载，使用进度键
        _download_to_file(url, source_tar, progress_key=progress_key)

        # 清理进度信息（延迟清理，给前端时间获取最终状态）
        def cleanup_progress():
            time.sleep(5)  # 5秒后清理
            with _progress_lock:
                _download_progress.pop(progress_key, None)

        threading.Thread(target=cleanup_progress, daemon=True).start()

    except Exception as e:
        # 清理错误进度
        with _progress_lock:
            _download_progress.pop(progress_key, None)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"下载源码包失败: {e}",
        )

    # 记录审计日志（仅记录下载）
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_source_download",
        target=version,
        details={
            "url": url,
            "success": True,
            "build_log_path": None,
        },
        ip_address=get_client_ip(request),
    )

    return NginxBuildResult(
        success=True,
        message=f"源码包下载成功，请在列表中对版本 {version} 执行编译",
        version=version,
        build_log_path=None,
    )


@router.post(
    "/versions/upload",
    response_model=NginxBuildResult,
    summary="上传 Nginx 源码包（不编译）",
)
async def upload_and_build_nginx_version(
    request: Request,
    file: UploadFile = File(...),
    version: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NginxBuildResult:
    """
    上传本地 Nginx 源码包。

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
    dest = _get_source_tar_path(version)

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

    # 记录审计日志（仅记录上传）
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_source_upload",
        target=version,
        details={
            "filename": filename,
            "success": True,
            "build_log_path": None,
        },
        ip_address=get_client_ip(request),
    )

    return NginxBuildResult(
        success=True,
        message=f"源码包上传成功，请在列表中对版本 {version} 执行编译",
        version=version,
        build_log_path=None,
    )


@router.post(
    "/versions/{version}/compile",
    response_model=NginxBuildResult,
    summary="编译已下载/上传的 Nginx 源码包",
)
async def compile_nginx_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NginxBuildResult:
    """
    使用已下载/上传的源码包编译安装指定版本 Nginx。

    要求：
    - build_root 中存在 nginx-<version>.tar.gz 或等价源码包
    - 编译成功后会在 versions_root/<version> 下生成完整安装目录
    """
    _ensure_nginx_dirs()
    source_tar = _get_source_tar_path(version)
    if not source_tar.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源码包不存在，请先通过在线下载或上传方式准备源码包",
        )

    result = _compile_nginx_from_source(source_tar, version)

    # 记录审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_compile",
        target=version,
        details={
            "source_tar": str(source_tar),
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
    """返回指定版本的编译日志内容。

    - 如果编译日志文件存在：返回最后一段内容
    - 如果不存在：返回空内容，而不是报错，方便前端展示“暂无日志”
    """
    log_path = _get_build_log_path(version)
    content = ""
    if log_path.exists():
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
        "content": content[-20000:] if content else "",
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
    - 使用编译版本自带的配置文件 <versions_root>/<version>/conf/nginx.conf
    - 编译后的 nginx 自带完整的配置文件，包括正确的 mime.types 等路径
    - 启动新版本前会自动停止所有其他正在运行的版本，确保系统只有一个nginx在运行
    - 所有版本共享统一的配置目录（conf.d）和静态文件目录（html），版本切换时配置和静态文件保持一致
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

    # 确保系统只有一个nginx在运行：先停止所有其他正在运行的版本
    all_versions = _list_all_versions()
    stopped_versions = []
    for v_info in all_versions:
        if v_info.version != version and v_info.running:
            # 停止其他正在运行的版本
            try:
                other_install_path = _get_install_path(v_info.version)
                other_executable = _get_nginx_executable(other_install_path)
                other_config_path = other_install_path / "conf" / "nginx.conf"
                
                stop_cmd = [
                    str(other_executable),
                    "-c",
                    str(other_config_path),
                    "-p",
                    str(other_install_path),
                    "-s",
                    "quit",
                ]
                subprocess.run(
                    stop_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                stopped_versions.append(v_info.version)
            except Exception as e:
                # 记录错误但继续执行
                pass

    # 确保必要目录存在（logs、conf 等）
    (install_path / "logs").mkdir(parents=True, exist_ok=True)

    # 确保统一的配置目录和静态文件目录存在，并创建默认配置
    conf_dir = Path(config.nginx.conf_dir)
    if not conf_dir.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        conf_dir = (backend_dir / conf_dir).resolve()
    conf_dir.mkdir(parents=True, exist_ok=True)
    
    static_dir = Path(config.nginx.static_dir)
    if not static_dir.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        static_dir = (backend_dir / static_dir).resolve()
    static_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果统一的配置目录中没有default.conf，创建默认配置
    default_conf_path = conf_dir / "default.conf"
    if not default_conf_path.exists():
        default_server_conf = f"""server {{
    listen 80;
    server_name _;

    root {static_dir};
    index index.html;

    # 防止 favicon.ico 等静态资源触发循环（必须在 location / 之前）
    location ~* \\.(ico|css|js|gif|jpe?g|png|svg|woff|woff2|ttf|eot)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
        try_files $uri =404;
    }}

    # 前端静态文件
    location / {{
        # 先尝试直接访问文件，再尝试作为目录，最后回退到 index.html
        try_files $uri $uri/ /index.html;
    }}

    # API 代理
    location /api/ {{
        proxy_pass http://127.0.0.1:{config.app.port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    # 健康检查
    location /health {{
        access_log off;
        return 200 "healthy\\n";
        add_header Content-Type text/plain;
    }}
}}
"""
        default_conf_path.write_text(default_server_conf, encoding="utf-8")

    # 使用编译版本自带的配置文件（conf/nginx.conf）
    # 编译后的 nginx 自带完整的配置文件，包括正确的 mime.types 路径
    version_config_path = install_path / "conf" / "nginx.conf"
    if not version_config_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本 {version} 的配置文件不存在: {version_config_path}",
        )
    
    # 确保nginx.conf已更新为使用统一的配置目录和静态文件目录
    # 检查配置文件中是否包含统一的配置目录路径，如果没有则更新
    config_content = version_config_path.read_text(encoding="utf-8")
    if str(conf_dir) not in config_content:
        _update_nginx_config_for_unified_dirs(install_path, version)

    # 先测试配置
    try:
        import subprocess

        test_cmd = [
            str(executable),
            "-t",
            "-c",
            str(version_config_path),
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

        # 使用编译版本自带的配置文件
        cmd = [
            str(executable),
            "-c",
            str(version_config_path),
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
    - 使用编译版本自带的配置文件 <versions_root>/<version>/conf/nginx.conf
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

        # 使用编译版本自带的配置文件
        version_config_path = install_path / "conf" / "nginx.conf"
        cmd = [
            str(executable),
            "-c",
            str(version_config_path),
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


@router.post(
    "/versions/{version}/force_stop",
    summary="强制停止指定版本的 Nginx（发送信号终止进程）",
)
async def force_stop_nginx_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    强制停止指定版本的 Nginx。

    优先使用 PID 文件精确终止：
    - 若存在 PID 文件且进程仍在运行，则先发送 SIGTERM，再尝试 SIGKILL。
    - 如 PID 文件不存在或进程已退出，则视为已停止。
    """
    install_path = _get_install_path(version)

    if not install_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本未正确安装: {version}",
        )

    pid_file = _get_pid_file(install_path)
    pid: Optional[int] = None

    if pid_file.exists():
        try:
            content = pid_file.read_text(encoding="utf-8").strip()
            if content:
                pid = int(content)
        except Exception:
            pid = None

    # 如果没拿到 PID，视为已经停止
    if pid is None:
        info = _get_version_status(version)
        return {
            "success": True,
            "message": f"Nginx 版本 {version} 已停止（无有效 PID）",
            "version": info,
        }

    # 先尝试优雅退出
    errors: list[str] = []
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        # 进程已不存在，视为成功
        pass
    except Exception as e:
        errors.append(f"SIGTERM 发送失败: {e}")

    # 简单等待一下查看是否退出
    time.sleep(0.5)
    if _check_process_running(pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception as e:
            errors.append(f"SIGKILL 发送失败: {e}")

    # 写入审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_force_stop",
        target=version,
        details={
            "install_path": str(install_path),
            "pid": pid,
            "errors": errors,
        },
        ip_address=get_client_ip(request),
    )

    info = _get_version_status(version)
    if _check_process_running(pid):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="尝试发送终止信号后进程仍在运行，请手动检查系统进程",
        )

    return {
        "success": True,
        "message": f"Nginx 版本 {version} 已强制停止",
        "version": info,
    }


@router.post(
    "/force_release_http_port",
    summary="强制释放 HTTP 端口（默认 80），终止占用该端口的进程",
)
async def force_release_http_port(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    port: int = 80,
):
    """
    强制释放指定 HTTP 端口（默认 80）。

    实现方式：
    - 调用 `lsof -t -iTCP:<port> -sTCP:LISTEN` 获取监听该端口的 PID 列表
    - 对每个 PID 发送 SIGTERM，然后必要时发送 SIGKILL
    注意：该能力较强，仅应授予有权限的用户使用。
    """
    try:
        cmd = ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"执行 lsof 失败: {e}",
        )

    if result.returncode not in (0, 1):
        # 1 表示没有匹配记录，也视为正常
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"lsof 调用错误: {result.stderr.strip() or result.stdout.strip()}",
        )

    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    pids: List[int] = []
    for line in lines:
        try:
            pids.append(int(line))
        except ValueError:
            continue

    if not pids:
        return {
            "success": True,
            "message": f"端口 {port} 当前没有进程在监听",
            "port": port,
            "pids": [],
        }

    results = _kill_pids(pids)

    # 审计
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_force_release_http_port",
        target=str(port),
        details={
            "port": port,
            "pids": pids,
            "results": results,
        },
        ip_address=get_client_ip(request),
    )

    return {
        "success": True,
        "message": f"已尝试终止占用端口 {port} 的进程",
        "port": port,
        "pids": pids,
        "results": results,
    }


@router.delete(
    "/versions/{version}",
    summary="删除指定版本的 Nginx（仅在未运行状态下允许）",
)
async def delete_nginx_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    删除指定版本的 Nginx。

    约束：
    - 若该版本仍在运行，则拒绝删除，提示先停止；
    - 删除内容包括：
      - 安装目录：<versions_root>/<version>
      - 对应构建目录：<build_root>/<version>
      - 对应编译日志文件（如存在）
    """
    install_path = _get_install_path(version)
    build_root = _get_build_root()
    build_dir = build_root / version
    log_path = _get_build_log_path(version)
    source_tar = _get_source_tar_path(version)

    info = _get_version_status(version)
    if info.running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Nginx 版本 {version} 正在运行，请先停止后再删除",
        )

    # 删除安装目录
    if install_path.exists():
        try:
            shutil.rmtree(install_path, ignore_errors=False)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"删除安装目录失败: {e}",
            )

    # 删除构建目录（忽略错误）
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)

    # 删除编译日志文件（忽略错误）
    if log_path.exists():
        try:
            log_path.unlink()
        except Exception:
            pass

    # 删除源码包（忽略错误），避免在列表中继续展示为“未编译”
    if source_tar.exists():
        try:
            source_tar.unlink()
        except Exception:
            pass

    # 审计
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_delete",
        target=version,
        details={
            "install_path": str(install_path),
            "build_dir": str(build_dir),
            "build_log_path": str(log_path),
            "source_tar": str(source_tar),
        },
        ip_address=get_client_ip(request),
    )

    return {
        "success": True,
        "message": f"Nginx 版本 {version} 已删除",
        "version": version,
    }
