"""
Nginx 多版本管理路由
"""

import os
import platform
import tarfile
import shutil
import subprocess
import signal
import time
import ssl
import threading
import re
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
    Body,
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
_VERSION_METADATA_FILENAME = ".nginx-version"


class NginxVersionInfo(BaseModel):
    """Nginx 版本信息"""

    directory: str  # 实际目录名称
    version: Optional[str] = None  # 二进制版本号
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


class CompileRequest(BaseModel):
    """编译请求"""

    custom_configure_args: Optional[str] = None  # 自定义configure参数，每行一个参数


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


def _get_last_started_version_file() -> Path:
    """获取最后启动版本记录文件路径"""
    return _get_versions_root() / ".last_started_version"


def _save_last_started_version(version: str) -> None:
    """保存最后启动的nginx版本"""
    try:
        version_file = _get_last_started_version_file()
        version_file.parent.mkdir(parents=True, exist_ok=True)
        version_file.write_text(version, encoding="utf-8")
    except Exception:
        # 保存失败不影响主流程
        pass


def _get_last_started_version() -> Optional[str]:
    """读取最后启动的nginx版本"""
    try:
        version_file = _get_last_started_version_file()
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
            if version:
                return version
    except Exception:
        pass
    return None


def _get_nginx_executable(install_path: Path) -> Path:
    """
    获取指定安装路径下的 Nginx 可执行文件

    约定：编译时使用 --prefix=<install_path>，则可执行文件位于 <install_path>/sbin/nginx
    """
    return install_path / "sbin" / "nginx"


def _get_version_metadata_path(install_path: Path) -> Path:
    """返回存储版本信息的元数据文件路径"""
    return install_path / _VERSION_METADATA_FILENAME


def _write_version_metadata(install_path: Path, version: str) -> None:
    """将版本号写入元数据文件，忽略写入失败"""
    version = (version or "").strip()
    if not version:
        return

    meta_path = _get_version_metadata_path(install_path)
    try:
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(version, encoding="utf-8")
    except Exception:
        # 忽略写入失败，避免影响主流程
        pass


def _detect_nginx_binary_version(executable: Path) -> Optional[str]:
    """通过执行 nginx -v 推断真实版本号"""
    if not executable.exists():
        return None

    try:
        result = subprocess.run(
            [str(executable), "-v"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None

    output = (result.stdout or "") + (result.stderr or "")
    if not output:
        return None

    match = re.search(r"nginx/([\w\.\-]+)", output)
    if match:
        return match.group(1)
    return None


def _resolve_version_label(
    directory: str, install_path: Path, executable: Path
) -> Optional[str]:
    """
    解析目录对应的版本号，优先使用元数据文件，其次使用目录名，最后尝试读取二进制。
    """
    meta_path = _get_version_metadata_path(install_path)
    if meta_path.exists():
        try:
            content = meta_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    # 目录名本身就是版本号的情况（例如 1.28.0）
    if directory != "last":
        return directory

    # last 目录需要从二进制中解析
    return _detect_nginx_binary_version(executable)


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


def _get_default_nginx_tar_path() -> Optional[Path]:
    """获取默认nginx压缩包路径（系统自带的）"""
    # 当前文件在 backend/app/routers/nginx_manager.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    default_tar = backend_dir / "default-nginx" / "nginx-1.29.3.tar.gz"
    if default_tar.exists():
        return default_tar
    return None


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

    # 生成新的配置内容
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


def _update_nginx_config_for_version(install_path: Path, version: str) -> None:
    """
    更新编译后的nginx.conf，使其使用版本目录下的配置目录和静态文件目录

    每个版本都有自己独立的配置目录（conf/conf.d）和静态文件目录（html），
    通过切换nginx版本来管理和使用不同的配置。
    """
    config = get_config()
    nginx_conf_path = install_path / "conf" / "nginx.conf"

    if not nginx_conf_path.exists():
        return

    # 使用版本目录下的 conf.d 配置目录
    conf_d_dir = install_path / "conf" / "conf.d"
    conf_d_dir.mkdir(parents=True, exist_ok=True)

    # 使用版本目录下的 html 静态文件目录
    html_dir = install_path / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    # 解析日志目录路径（日志可以统一放在一个地方）
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

    # 确保日志目录存在
    log_dir.mkdir(parents=True, exist_ok=True)

    # 读取原始配置（可能包含一些自定义设置）
    original_content = nginx_conf_path.read_text(encoding="utf-8")

    # 生成新的配置内容
    # 保留基本的worker_processes、events等配置
    # 但修改http块中的配置，使其指向版本目录下的配置
    new_config = f"""#user  nobody;
worker_processes  auto;

pid        logs/nginx.pid;

events {{
    worker_connections  1024;
}}

http {{
    include       mime.types;
    default_type  application/octet-stream;

    access_log  {access_log};
    error_log   {error_log};

    sendfile        on;
    keepalive_timeout  65;

    gzip  on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss;

    # 使用版本目录下的配置目录（每个版本独立）
    include conf.d/*.conf;
}}
"""

    # 写入新配置
    nginx_conf_path.write_text(new_config, encoding="utf-8")

    # 如果 conf.d 目录下没有 default.conf，创建一个默认配置
    default_conf_path = conf_d_dir / "default.conf"
    if not default_conf_path.exists():
        default_server_conf = f"""server {{
    listen 80;
    server_name _;

    root html;
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


def _backup_protected_dirs(install_path: Path) -> Dict[str, Path]:
    """
    备份需要保护的目录（静态文件、配置文件等）

    Returns:
        dict: {
            "html": Path,  # 备份的html目录路径
            "conf": Path,   # 备份的conf目录路径
            "logs": Path,   # 备份的logs目录路径
        }
    """
    backup_dir = install_path.parent / f"{install_path.name}_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backups = {}

    # 备份 html 目录（静态文件）
    html_dir = install_path / "html"
    if html_dir.exists() and any(html_dir.iterdir()):
        html_backup = backup_dir / "html"
        if html_backup.exists():
            shutil.rmtree(html_backup, ignore_errors=True)
        shutil.copytree(html_dir, html_backup, dirs_exist_ok=True)
        backups["html"] = html_backup

    # 备份 conf 目录（配置文件，但排除nginx.conf，因为会重新生成）
    conf_dir = install_path / "conf"
    if conf_dir.exists():
        conf_backup = backup_dir / "conf"
        if conf_backup.exists():
            shutil.rmtree(conf_backup, ignore_errors=True)
        conf_backup.mkdir(parents=True, exist_ok=True)
        # 只备份非nginx.conf的配置文件
        for item in conf_dir.iterdir():
            if item.name != "nginx.conf":
                if item.is_dir():
                    shutil.copytree(item, conf_backup / item.name, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, conf_backup / item.name)
        if any(conf_backup.iterdir()):
            backups["conf"] = conf_backup

    # 备份 logs 目录（日志文件）
    logs_dir = install_path / "logs"
    if logs_dir.exists() and any(logs_dir.iterdir()):
        logs_backup = backup_dir / "logs"
        if logs_backup.exists():
            shutil.rmtree(logs_backup, ignore_errors=True)
        shutil.copytree(logs_dir, logs_backup, dirs_exist_ok=True)
        backups["logs"] = logs_backup

    return backups


def _upgrade_to_production_version(version: str) -> Dict[str, any]:
    """
    将指定版本升级到运行版（复制到 last 目录）

    升级过程：
    1. 检查版本是否已编译
    2. 备份 last 目录中的静态文件和配置文件
    3. 从版本目录复制到 last 目录
    4. 恢复备份的静态文件和配置文件

    Returns:
        dict: {
            "success": bool,
            "message": str,
            "version": str
        }
    """
    source_install_path = _get_install_path(version)
    target_install_path = _get_versions_root() / "last"

    # 检查源版本是否存在且已编译
    executable = _get_nginx_executable(source_install_path)
    if not source_install_path.exists() or not executable.exists():
        return {
            "success": False,
            "message": f"Nginx 版本 {version} 未编译，请先编译该版本",
            "version": version,
        }

    try:
        # 如果目标目录已存在，备份需要保护的文件
        backups = {}
        if target_install_path.exists() and any(target_install_path.iterdir()):
            backups = _backup_protected_dirs(target_install_path)

        # 删除目标目录（如果存在）
        if target_install_path.exists():
            shutil.rmtree(target_install_path, ignore_errors=True)

        # 复制整个版本目录到 last 目录
        shutil.copytree(source_install_path, target_install_path, dirs_exist_ok=True)

        # 如果有备份，恢复备份的文件
        if backups:
            _restore_protected_dirs(target_install_path, backups)

            # 清理备份目录
            backup_dir = (
                target_install_path.parent / f"{target_install_path.name}_backup"
            )
            if backup_dir.exists():
                try:
                    shutil.rmtree(backup_dir, ignore_errors=True)
                except Exception:
                    pass

        # 更新 last 目录的 nginx.conf 并记录真实版本号
        _update_nginx_config_for_version(target_install_path, version)
        _write_version_metadata(target_install_path, version)

        return {
            "success": True,
            "message": f"版本 {version} 已成功升级到运行版",
            "version": version,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"升级到运行版失败: {str(e)}",
            "version": version,
        }


def _restore_protected_dirs(install_path: Path, backups: Dict[str, Path]) -> None:
    """
    恢复备份的目录到安装路径
    """
    for key, backup_path in backups.items():
        target_dir = install_path / key
        if backup_path.exists():
            if target_dir.exists():
                # 合并目录内容，不覆盖已存在的文件
                for item in backup_path.iterdir():
                    target_item = target_dir / item.name
                    if item.is_dir():
                        if target_item.exists():
                            # 递归合并目录
                            for subitem in item.rglob("*"):
                                rel_path = subitem.relative_to(item)
                                target_subitem = target_item / rel_path
                                if subitem.is_dir():
                                    target_subitem.mkdir(parents=True, exist_ok=True)
                                else:
                                    target_subitem.parent.mkdir(
                                        parents=True, exist_ok=True
                                    )
                                    shutil.copy2(subitem, target_subitem)
                        else:
                            shutil.copytree(item, target_item, dirs_exist_ok=True)
                    else:
                        # 只复制不存在的文件
                        if not target_item.exists():
                            shutil.copy2(item, target_item)
            else:
                # 目标目录不存在，直接复制整个目录
                shutil.copytree(backup_path, target_dir, dirs_exist_ok=True)


def _compile_nginx_from_source(
    source_tar: Path,
    version: str,
    custom_configure_args: Optional[List[str]] = None,
    log_callback: Optional[Callable[[str], None]] = None,
) -> NginxBuildResult:
    """
    从源码编译安装 Nginx

    Args:
        source_tar: 源码 tar.gz 文件路径
        version: 目标版本号
        custom_configure_args: 用户自定义的configure参数列表
        log_callback: 日志回调函数，用于实时输出日志
    """
    _ensure_nginx_dirs()
    build_root = _get_build_root()

    logs: list[str] = []

    def _log(message: str):
        """内部日志函数，同时写入logs列表和回调"""
        logs.append(message)
        if log_callback:
            log_callback(message)

    install_path = _get_install_path(
        version
    )  # 最终对外暴露的安装目录：<versions_root>/<version>
    build_dir = build_root / version  # 源码解压与编译目录：<build_root>/<version>
    tmp_install_path = build_root / f"{version}_install_tmp"  # 编译安装使用的临时目录

    # 如果目标版本已经存在，先备份并清理（允许重新编译）
    if install_path.exists() and any(install_path.iterdir()):
        _log(f"检测到版本 {version} 已存在，将覆盖现有版本...")
        try:
            # 创建备份目录
            backup_path = install_path.parent / f"{version}_backup_{int(time.time())}"
            if backup_path.exists():
                shutil.rmtree(backup_path, ignore_errors=True)
            shutil.move(str(install_path), str(backup_path))
            _log(f"已将现有版本备份到: {backup_path}")
        except Exception as e:
            _log(f"备份现有版本失败: {e}，尝试直接删除...")
            shutil.rmtree(install_path, ignore_errors=True)

    # 清理并创建构建目录
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)
    build_dir.mkdir(parents=True, exist_ok=True)

    # 确保临时安装目录干净
    if tmp_install_path.exists():
        shutil.rmtree(tmp_install_path, ignore_errors=True)

    try:
        _log(f"使用源码包: {source_tar}")

        # 解压源码
        if not source_tar.exists():
            raise RuntimeError(f"源码包不存在: {source_tar}")

        _log("正在解压源码包...")
        with tarfile.open(source_tar, "r:gz") as tar:
            tar.extractall(build_dir)
        _log(f"已解压到构建目录: {build_dir}")

        source_dir = _detect_source_dir(build_dir)
        _log(f"检测到源码目录: {source_dir}")

        _log(f"临时安装路径: {tmp_install_path}")

        # 默认的configure参数
        default_configure_args = [
            # HTTP核心模块
            "--with-http_ssl_module",  # SSL/TLS支持
            "--with-http_realip_module",  # 真实IP模块
            "--with-http_addition_module",  # 响应添加模块
            "--with-http_sub_module",  # 响应替换模块
            "--with-http_dav_module",  # WebDAV支持
            "--with-http_flv_module",  # FLV流媒体支持
            "--with-http_mp4_module",  # MP4流媒体支持
            "--with-http_gunzip_module",  # Gunzip支持
            "--with-http_gzip_static_module",  # Gzip静态支持
            "--with-http_auth_request_module",  # 认证请求模块
            "--with-http_random_index_module",  # 随机索引模块
            "--with-http_secure_link_module",  # 安全链接模块
            "--with-http_degradation_module",  # 降级模块
            "--with-http_slice_module",  # 切片模块
            "--with-http_stub_status_module",  # 状态模块
            "--with-http_v2_module",  # HTTP/2支持
            # Stream模块（TCP/UDP代理）
            "--with-stream",
            "--with-stream_ssl_module",  # Stream SSL支持
            "--with-stream_realip_module",  # Stream真实IP模块
            "--with-stream_ssl_preread_module",  # Stream SSL预读模块
        ]

        # 合并默认参数和用户自定义参数
        # --prefix 必须由后台决定，用户不能覆盖
        configure_cmd = ["./configure", f"--prefix={tmp_install_path}"]

        # 添加默认参数
        configure_cmd.extend(default_configure_args)

        # 添加用户自定义参数（排除--prefix，因为由后台决定）
        if custom_configure_args:
            for arg in custom_configure_args:
                arg = arg.strip()
                if arg and not arg.startswith("--prefix"):
                    configure_cmd.append(arg)

        _log(f"执行配置命令: {' '.join(configure_cmd)}")
        _log("=" * 80)
        result = subprocess.run(
            configure_cmd,
            cwd=source_dir,
            capture_output=True,
            text=True,
        )
        _log(result.stdout)
        if result.stderr:
            _log(result.stderr)
        if result.returncode != 0:
            raise RuntimeError("configure 失败")
        _log("配置完成！")
        _log("=" * 80)

        # make
        make_cmd = ["make", "-j", str(os.cpu_count() or 1)]
        _log(f"执行编译命令: {' '.join(make_cmd)}")
        _log("=" * 80)
        # make命令输出较多，实时输出
        process = subprocess.Popen(
            make_cmd,
            cwd=source_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        for line in process.stdout:
            _log(line.rstrip())
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("make 失败")
        _log("编译完成！")
        _log("=" * 80)

        # make install
        install_cmd = ["make", "install"]
        _log(f"执行安装命令: {' '.join(install_cmd)}")
        _log("=" * 80)
        process = subprocess.Popen(
            install_cmd,
            cwd=source_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )
        for line in process.stdout:
            _log(line.rstrip())
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("make install 失败")
        _log("安装完成！")
        _log("=" * 80)

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

        # 修改编译后的nginx.conf，使其使用版本目录下的配置目录和静态文件目录
        _update_nginx_config_for_version(install_path, version)
        _log("已更新nginx.conf以使用版本目录下的配置目录和静态文件目录")

        # 记录真实版本号，供后续展示与 last 目录识别
        _write_version_metadata(install_path, version)
        _log("编译安装完成！")

        full_log = "\n".join(logs)
        log_path = _write_build_log(version, full_log)
        return NginxBuildResult(
            success=True,
            message=f"Nginx {version} 编译安装成功",
            version=version,
            build_log_path=str(log_path),
        )
    except Exception as e:
        _log(f"编译过程出错: {e}")
        import traceback

        _log(traceback.format_exc())
        full_log = "\n".join(logs)
        log_path = _write_build_log(version, full_log)
        return NginxBuildResult(
            success=False,
            message=f"编译安装失败: {e}",
            version=version,
            build_log_path=str(log_path),
        )


def _get_version_status(directory: str) -> NginxVersionInfo:
    """获取单个目录对应的版本状态信息"""
    # 内部使用绝对路径进行检测和编译
    install_path = _get_install_path(directory)
    executable = _get_nginx_executable(install_path)
    source_tar = _get_source_tar_path(directory)

    # 对外返回时，安装路径使用相对于配置的 versions_root 的“原始路径”，避免在 API 中暴露绝对路径
    raw_root = _get_versions_root_raw()
    display_install_path = str(raw_root / directory)
    display_executable = str(raw_root / directory / "sbin" / "nginx")
    resolved_version = _resolve_version_label(directory, install_path, executable)

    if not install_path.exists():
        return NginxVersionInfo(
            directory=directory,
            version=resolved_version,
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
            directory=directory,
            version=resolved_version,
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
        directory=directory,
        version=resolved_version,
        install_path=display_install_path,
        executable=display_executable,
        running=running,
        pid=pid,
        compiled=executable.exists(),
        has_source=source_tar.exists(),
    )


def _start_nginx_version_internal(version: str) -> Dict[str, any]:
    """
    内部函数：启动指定版本的 Nginx（不依赖HTTP请求和用户认证）

    Returns:
        dict: {
            "success": bool,
            "message": str,
            "version": Optional[str]
        }
    """
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)
    config = get_config()

    if not install_path.exists() or not executable.exists():
        return {
            "success": False,
            "message": f"Nginx 版本未正确安装: {version}",
            "version": None,
        }

    # 检查是否已经在运行
    current_info = _get_version_status(version)
    if current_info.running:
        return {
            "success": True,
            "message": f"Nginx 版本 {version} 已在运行",
            "version": version,
        }

    # 确保系统只有一个nginx在运行：先停止所有其他正在运行的版本
    all_versions = _list_all_versions()
    for v_info in all_versions:
        if v_info.directory != version and v_info.running:
            # 停止其他正在运行的版本
            try:
                other_install_path = _get_install_path(v_info.directory)
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
            except Exception:
                # 忽略错误，继续执行
                pass

    # 确保必要目录存在（logs、conf、html 等）
    (install_path / "logs").mkdir(parents=True, exist_ok=True)
    (install_path / "conf" / "conf.d").mkdir(parents=True, exist_ok=True)
    (install_path / "html").mkdir(parents=True, exist_ok=True)

    # 使用版本目录下的配置文件（conf/nginx.conf）
    # 注意：
    # - 如果文件不存在，则为该版本创建一个默认模板；
    # - 如果文件已存在，则视为“用户/配置管理页面”已经写入了期望的内容，不再做任何覆盖，
    #   以免重启 Nginx 时把已生效的配置还原成模板。
    version_config_path = install_path / "conf" / "nginx.conf"
    if not version_config_path.exists():
        _update_nginx_config_for_version(install_path, version)

    # 先测试配置
    try:
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
            return {
                "success": False,
                "message": f"配置测试失败: {output}",
                "version": None,
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"配置测试出错: {str(e)}",
            "version": None,
        }

    # 启动 Nginx（作为守护进程，由其自己在后台运行）
    try:
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
            return {
                "success": False,
                "message": f"Nginx 启动失败: {output}",
                "version": None,
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"Nginx 启动出错: {str(e)}",
            "version": None,
        }

    # 记录最后启动的版本
    _save_last_started_version(version)

    return {
        "success": True,
        "message": f"Nginx 版本 {version} 启动成功",
        "version": version,
    }


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

    # 初始化进度（仅在不存在时初始化，避免覆盖已有的初始化）
    if progress_key:
        with _progress_lock:
            if progress_key not in _download_progress:
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
    "/versions/latest",
    summary="获取 Nginx 官方最新版本列表",
)
async def get_latest_nginx_versions(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
):
    """
    从 nginx.org/download/ 获取最新的 Nginx 版本列表

    Args:
        limit: 返回的版本数量，默认5个

    Returns:
        {
            "success": bool,
            "versions": List[str],  # 版本号列表，如 ["1.28.0", "1.26.2", ...]
            "message": str
        }
    """
    try:
        import httpx
        from bs4 import BeautifulSoup

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://nginx.org/download/")
            response.raise_for_status()

            # 解析 HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # 查找所有 nginx-*.tar.gz 链接
            version_pattern = re.compile(r"nginx-(\d+\.\d+\.\d+)\.tar\.gz")
            versions = []

            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                match = version_pattern.search(href)
                if match:
                    version = match.group(1)
                    if version not in versions:
                        versions.append(version)

            # 按版本号排序（降序，最新的在前）
            def version_key(v):
                parts = v.split(".")
                return tuple(int(p) for p in parts)

            versions.sort(key=version_key, reverse=True)

            # 返回最新的 limit 个版本
            latest_versions = versions[:limit]

            return {
                "success": True,
                "versions": latest_versions,
                "message": f"成功获取 {len(latest_versions)} 个最新版本",
            }
    except ImportError:
        return {
            "success": False,
            "versions": [],
            "message": "缺少依赖包，请安装 httpx 和 beautifulsoup4",
        }
    except Exception as e:
        return {
            "success": False,
            "versions": [],
            "message": f"获取最新版本列表失败: {str(e)}",
        }


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


@router.get(
    "/versions/{version}/config",
    summary="获取指定版本的 nginx.conf 配置内容",
)
async def get_nginx_version_config(
    version: str,
    current_user: User = Depends(get_current_user),
):
    """
    读取指定 Nginx 版本目录下的核心配置文件内容：
    - 路径约定为 <versions_root>/<version>/conf/nginx.conf
    - 仅做只读展示，不做任何写入或格式化
    """
    install_path = _get_install_path(version)
    if not install_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本未安装: {version}",
        )

    nginx_conf_path = install_path / "conf" / "nginx.conf"
    if not nginx_conf_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"配置文件不存在: {nginx_conf_path}",
        )

    try:
        content = nginx_conf_path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"读取配置文件失败: {e}",
        )

    # 对外返回展示路径时，保持与 list 版本接口中的 install_path 风格一致（相对 versions_root）
    raw_root = _get_versions_root_raw()
    display_config_path = str(raw_root / version / "conf" / "nginx.conf")

    return {
        "success": True,
        "version": version,
        "config_path": display_config_path,
        "content": content,
    }


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

    # 检查是否已经在下载中
    with _progress_lock:
        existing_progress = _download_progress.get(progress_key)
        if existing_progress and existing_progress.get("status") == "downloading":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"版本 {version} 的下载任务已在进行中",
            )

    # 初始化进度状态
    with _progress_lock:
        _download_progress[progress_key] = {
            "status": "downloading",
            "downloaded": 0,
            "total": None,
            "percentage": 0,
            "error": None,
        }

    def download_task():
        """后台下载任务"""
        try:
            # 执行下载
            _download_to_file(url, source_tar, progress_key=progress_key)

            # 记录审计日志（仅记录下载）
            # 注意：这里不能直接访问 db 和 current_user，需要在主线程中记录
            # 或者在下载完成后通过其他方式记录

        except Exception as e:
            # 标记错误
            with _progress_lock:
                if progress_key in _download_progress:
                    _download_progress[progress_key].update(
                        {"status": "error", "error": str(e)}
                    )

    # 在后台线程中启动下载任务
    download_thread = threading.Thread(target=download_task, daemon=True)
    download_thread.start()

    # 等待一小段时间，确保下载任务已启动
    time.sleep(0.1)

    # 记录审计日志（记录下载任务已启动）
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_source_download",
        target=version,
        details={
            "url": url,
            "status": "started",
            "build_log_path": None,
        },
        ip_address=get_client_ip(request),
    )

    # 清理进度信息（延迟清理，给前端时间获取最终状态）
    def cleanup_progress():
        # 等待下载完成（最多等待1小时）
        max_wait_time = 3600
        wait_interval = 2
        waited = 0
        while waited < max_wait_time:
            with _progress_lock:
                progress = _download_progress.get(progress_key)
                if not progress:
                    break
                status = progress.get("status")
                if status in ("completed", "error"):
                    time.sleep(5)  # 再等待5秒，给前端时间获取最终状态
                    break
            time.sleep(wait_interval)
            waited += wait_interval

        # 清理进度信息
        with _progress_lock:
            _download_progress.pop(progress_key, None)

    threading.Thread(target=cleanup_progress, daemon=True).start()

    # 立即返回，告诉前端下载已开始
    return NginxBuildResult(
        success=True,
        message=f"下载任务已启动，请通过进度接口查看下载进度",
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
    summary="编译已下载/上传的 Nginx 源码包（流式输出）",
)
async def compile_nginx_version(
    version: str,
    compile_request: CompileRequest = Body(default=CompileRequest()),
    request: Request = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    使用已下载/上传的源码包编译安装指定版本 Nginx（支持实时日志流式输出）。

    要求：
    - build_root 中存在 nginx-<version>.tar.gz 或等价源码包
    - 编译成功后会在 versions_root/<version> 下生成完整安装目录
    - 编译完成后，可以通过 /versions/{version}/upgrade-to-production 接口升级到运行版

    支持自定义configure参数（custom_configure_args），每行一个参数。
    --prefix参数由系统自动设置，不能覆盖。
    """
    _ensure_nginx_dirs()
    source_tar = _get_source_tar_path(version)
    if not source_tar.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="源码包不存在，请先通过在线下载或上传方式准备源码包",
        )

    # 解析用户自定义的configure参数
    custom_args = []
    if compile_request.custom_configure_args:
        custom_args = [
            line.strip()
            for line in compile_request.custom_configure_args.split("\n")
            if line.strip() and not line.strip().startswith("--prefix")
        ]

    async def generate_logs():
        """生成器函数，实时输出编译日志"""
        import asyncio
        import queue
        from concurrent.futures import ThreadPoolExecutor

        # 创建一个队列来收集日志
        log_queue = queue.Queue()
        compile_done = False
        compile_result = None

        def log_callback_thread(message: str):
            """日志回调函数（在线程中调用）"""
            log_queue.put(message)

        try:
            # 开始编译
            yield f"data: 开始编译 Nginx {version}...\n\n"

            # 使用线程执行编译
            executor = ThreadPoolExecutor(max_workers=1)

            future = executor.submit(
                _compile_nginx_from_source,
                source_tar,
                version,
                custom_args,
                log_callback_thread,
            )

            # 实时发送日志
            while not compile_done:
                try:
                    # 等待日志或编译完成
                    try:
                        log_message = log_queue.get(timeout=0.5)
                        # 转义特殊字符，发送SSE格式
                        escaped_msg = (
                            log_message.replace("\n", "\\n")
                            .replace("\r", "\\r")
                            .replace("\0", "")
                        )
                        yield f"data: {escaped_msg}\n\n"
                    except queue.Empty:
                        if future.done():
                            compile_done = True
                            break
                        # 继续等待
                        await asyncio.sleep(0.1)
                except Exception as e:
                    yield f"data: [ERROR] 日志读取错误: {str(e)}\n\n"

            # 获取编译结果
            result = future.result()
            compile_result = result

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
                    "custom_args": custom_args,
                },
                ip_address=get_client_ip(request),
            )

            # 发送最终结果
            if result.success:
                yield f"data: [SUCCESS] 编译成功！\n\n"
            else:
                yield f"data: [ERROR] {result.message}\n\n"

            executor.shutdown(wait=False)

        except Exception as e:
            import traceback

            error_msg = f"编译过程异常: {str(e)}\n{traceback.format_exc()}"
            yield f"data: [ERROR] {error_msg}\n\n"

    return StreamingResponse(
        generate_logs(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用nginx缓冲
        },
    )


@router.post(
    "/versions/{version}/upgrade-to-production",
    summary="将指定版本升级到运行版",
)
async def upgrade_to_production_version(
    version: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    将指定版本升级到运行版（复制到 last 目录）。

    要求：
    - 版本必须已编译完成
    - 升级过程会保留运行版（last 目录）中的静态文件和配置文件
    - 升级后需要手动重启 nginx 才能使用新版本
    """
    # 检查版本是否已编译
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)

    if not install_path.exists() or not executable.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本 {version} 未编译，请先编译该版本",
        )

    # 执行升级
    result = _upgrade_to_production_version(version)

    # 记录审计日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_version_upgrade_to_production",
        target=version,
        details={
            "success": result["success"],
            "message": result["message"],
        },
        ip_address=get_client_ip(request),
    )

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result["message"],
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
    "/versions/{version}/compile-progress",
    summary="获取编译进度",
)
async def get_compile_progress(
    version: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取指定版本的编译进度

    通过检查编译日志和文件系统状态来判断编译进度
    """
    log_path = _get_build_log_path(version)
    build_root = _get_build_root()
    build_dir = build_root / version
    install_path = _get_install_path(version)
    executable = _get_nginx_executable(install_path)

    progress = 0
    stage = "等待开始"
    message = ""

    # 检查是否已编译完成
    if install_path.exists() and executable.exists():
        progress = 100
        stage = "编译完成"
        message = "Nginx 已成功编译"
        return {
            "progress": progress,
            "stage": stage,
            "message": message,
            "completed": True,
        }

    # 检查编译日志
    log_size = 0
    if log_path.exists():
        try:
            log_size = log_path.stat().st_size
            log_content = log_path.read_text(encoding="utf-8", errors="ignore")

            # 先检查错误情况
            if "configure 失败" in log_content:
                progress = 20
                stage = "配置失败"
                message = "配置阶段失败，请查看日志"
                return {
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "completed": False,
                    "error": True,
                }
            if "make 失败" in log_content:
                progress = 50
                stage = "编译失败"
                message = "编译阶段失败，请查看日志"
                return {
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "completed": False,
                    "error": True,
                }
            if "make install 失败" in log_content:
                progress = 80
                stage = "安装失败"
                message = "安装阶段失败，请查看日志"
                return {
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "completed": False,
                    "error": True,
                }
            if "编译过程出错" in log_content:
                progress = max(progress, 10)
                stage = "编译出错"
                message = "编译过程中出现错误，请查看日志"
                return {
                    "progress": progress,
                    "stage": stage,
                    "message": message,
                    "completed": False,
                    "error": True,
                }

            # 根据日志内容判断进度（按顺序检查，确保进度递增）
            # 检查是否已完成安装
            if (
                "已将临时安装目录移动到正式路径" in log_content
                or "已更新nginx.conf" in log_content
            ):
                progress = 95
                stage = "完成安装"
                message = "正在完成最后的配置..."
            # 检查是否在执行安装
            elif "执行安装命令" in log_content or "make install" in log_content:
                progress = 80
                stage = "安装中"
                message = "正在安装到目标目录..."
            # 检查是否在编译中
            elif "执行编译命令" in log_content:
                # 编译阶段，根据日志大小和内容估算进度
                # make阶段通常比较长，根据日志增长来估算
                base_progress = 50
                # 如果日志中有make的输出，说明正在编译
                if "cc " in log_content or "linking" in log_content.lower():
                    # 编译正在进行，根据日志行数或大小估算
                    line_count = len(log_content.splitlines())
                    # 假设编译过程会产生大量输出，根据行数估算
                    if line_count > 100:
                        # 编译进行中，进度在50-70之间
                        progress = min(70, base_progress + int((line_count - 100) / 10))
                    else:
                        progress = base_progress
                else:
                    progress = base_progress
                stage = "编译中"
                message = f"正在编译 Nginx（已处理 {line_count if 'line_count' in locals() else 0} 行输出）..."
            # 检查是否在配置
            elif "执行配置命令" in log_content or "configure" in log_content.lower():
                progress = 30
                stage = "配置环境"
                message = "正在配置编译环境..."
            # 检查是否已解压
            elif "已解压到构建目录" in log_content or "检测到源码目录" in log_content:
                progress = 15
                stage = "解压源码"
                message = "源码包已解压，准备配置..."
        except Exception as e:
            # 读取日志失败，尝试通过文件系统判断
            pass

    # 通过文件系统和日志大小判断进度（用于实时更新）
    if build_dir.exists():
        source_dirs = [
            d for d in build_dir.iterdir() if d.is_dir() and d.name.startswith("nginx-")
        ]
        if source_dirs:
            source_dir = source_dirs[0]
            # 检查是否有编译产物
            if (source_dir / "objs").exists():
                # 有编译目录，说明configure已完成
                progress = max(progress, 35)
                # 检查编译产物数量来估算编译进度
                objs_dir = source_dir / "objs"
                if objs_dir.exists():
                    obj_files = list(objs_dir.glob("*.o"))
                    # 假设nginx编译会产生约100-200个目标文件
                    if len(obj_files) > 0:
                        # 根据目标文件数量估算编译进度
                        estimated_progress = min(70, 35 + int(len(obj_files) / 3))
                        progress = max(progress, estimated_progress)
                        stage = "编译中"
                        message = f"正在编译（已生成 {len(obj_files)} 个目标文件）..."

            # 如果日志文件在增长，说明编译正在进行
            if log_size > 0 and progress < 50:
                # 根据日志大小估算进度（粗略估算）
                # 假设完整编译日志大约50-100KB
                if log_size > 50000:  # 50KB
                    progress = max(progress, 60)
                elif log_size > 20000:  # 20KB
                    progress = max(progress, 45)
                elif log_size > 5000:  # 5KB
                    progress = max(progress, 30)

    # 通过文件系统判断
    if build_dir.exists():
        source_dirs = [
            d for d in build_dir.iterdir() if d.is_dir() and d.name.startswith("nginx-")
        ]
        if source_dirs:
            progress = max(progress, 15)
            stage = "源码已解压"
            message = "源码包已解压，准备配置..."

    return {
        "progress": progress,
        "stage": stage,
        "message": message,
        "completed": False,
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
        if v_info.directory != version and v_info.running:
            # 停止其他正在运行的版本
            try:
                other_install_path = _get_install_path(v_info.directory)
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
                stopped_versions.append(v_info.directory)
            except Exception as e:
                # 记录错误但继续执行
                pass

    # 确保必要目录存在（logs、conf、html 等）
    (install_path / "logs").mkdir(parents=True, exist_ok=True)
    (install_path / "conf" / "conf.d").mkdir(parents=True, exist_ok=True)
    (install_path / "html").mkdir(parents=True, exist_ok=True)

    # 使用版本目录下的配置文件（conf/nginx.conf）
    version_config_path = install_path / "conf" / "nginx.conf"
    if not version_config_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nginx 版本 {version} 的配置文件不存在: {version_config_path}",
        )

    # IMPORTANT:
    # 为了保证“配置管理”页面写入并重载后的配置在后续重启 Nginx 时不会被还原，
    # 这里不再对已经存在的 nginx.conf 做任何自动重写或模板覆盖。
    # 如果需要使用 conf.d/*.conf，可以在初始模板或通过配置管理显式添加。

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

    # 记录最后启动的版本
    _save_last_started_version(version)

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


def _get_port_pids(port: int) -> List[int]:
    """
    获取占用指定端口的进程PID列表

    Args:
        port: 端口号

    Returns:
        占用该端口的进程PID列表
    """
    system = platform.system().lower()
    pids: List[int] = []

    try:
        if system == "windows":
            # Windows 使用 netstat 命令
            cmd = ["netstat", "-ano"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"netstat 调用错误: {result.stderr.strip() or result.stdout.strip()}",
                )

            # 解析 netstat 输出，查找监听指定端口的进程
            # 格式示例: TCP    0.0.0.0:80             0.0.0.0:0              LISTENING       1234
            # 或者: TCP    [::]:80                 [::]:0                 LISTENING       1234
            lines = result.stdout.splitlines()
            for line in lines:
                # 检查是否包含端口号和 LISTENING 状态
                if f":{port}" in line and "LISTENING" in line.upper():
                    # 分割行，PID 通常在最后一列
                    parts = line.split()
                    if len(parts) >= 5:
                        try:
                            # 尝试从最后一列获取 PID
                            pid = int(parts[-1])
                            if pid > 0:  # 确保 PID 有效
                                pids.append(pid)
                        except (ValueError, IndexError):
                            continue
        else:
            # Linux/macOS 使用 lsof 命令
            cmd = ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode not in (0, 1):
                # 1 表示没有匹配记录，也视为正常
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"lsof 调用错误: {result.stderr.strip() or result.stdout.strip()}",
                )

            lines = [
                line.strip() for line in result.stdout.splitlines() if line.strip()
            ]
            for line in lines:
                try:
                    pids.append(int(line))
                except ValueError:
                    continue
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"执行端口查询失败 ({system}): {e}",
        )

    # 去重 PID 列表
    return list(set(pids))


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
    - Linux/macOS: 调用 `lsof -t -iTCP:<port> -sTCP:LISTEN` 获取监听该端口的 PID 列表
    - Windows: 调用 `netstat -ano | findstr :<port>` 获取监听该端口的 PID 列表
    - 对每个 PID 发送 SIGTERM，然后必要时发送 SIGKILL
    注意：该能力较强，仅应授予有权限的用户使用。
    """
    pids = _get_port_pids(port)

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


@router.post(
    "/force_release_nginx_ports",
    summary="强制释放Nginx端口（80和443），终止占用这些端口的进程",
)
async def force_release_nginx_ports(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    强制释放Nginx常用的80和443端口，终止占用这些端口的进程。

    实现方式：
    - Linux/macOS: 调用 `lsof -t -iTCP:<port> -sTCP:LISTEN` 获取监听该端口的 PID 列表
    - Windows: 调用 `netstat -ano | findstr :<port>` 获取监听该端口的 PID 列表
    - 对每个 PID 发送 SIGTERM，然后必要时发送 SIGKILL

    注意：该能力较强，仅应授予有权限的用户使用。
    """
    ports = [80, 443]
    all_pids: List[int] = []
    port_results = {}

    # 获取所有端口的PID
    for port in ports:
        try:
            pids = _get_port_pids(port)
            if pids:
                all_pids.extend(pids)
                port_results[port] = {"pids": pids, "count": len(pids)}
            else:
                port_results[port] = {"pids": [], "count": 0}
        except Exception as e:
            port_results[port] = {"pids": [], "count": 0, "error": str(e)}

    # 去重所有PID（同一个进程可能占用多个端口）
    all_pids = list(set(all_pids))

    if not all_pids:
        # 审计
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="nginx_force_release_nginx_ports",
            target="80,443",
            details={
                "ports": ports,
                "port_results": port_results,
                "pids": [],
            },
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "端口80和443当前没有进程在监听",
            "ports": ports,
            "pids": [],
            "port_results": port_results,
        }

    # 终止所有进程
    kill_results = _kill_pids(all_pids)

    # 更新端口结果，添加终止结果
    for port in ports:
        if port in port_results:
            port_pids = port_results[port]["pids"]
            port_results[port]["kill_results"] = {
                pid: kill_results.get(pid, {})
                for pid in port_pids
                if pid in kill_results
            }

    # 审计
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="nginx_force_release_nginx_ports",
        target="80,443",
        details={
            "ports": ports,
            "pids": all_pids,
            "port_results": port_results,
            "kill_results": kill_results,
        },
        ip_address=get_client_ip(request),
    )

    port_summary = ", ".join(
        [f"{port}({port_results[port]['count']}个进程)" for port in ports]
    )

    return {
        "success": True,
        "message": f"已尝试终止占用端口{port_summary}的进程",
        "ports": ports,
        "pids": all_pids,
        "port_results": port_results,
        "kill_results": kill_results,
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


@router.get(
    "/setup/check",
    summary="检查初始设置状态",
)
async def check_setup_status(
    current_user: User = Depends(get_current_user),
):
    """
    检查系统初始设置状态：
    - 是否有已编译的nginx版本
    - 是否有默认nginx压缩包可用
    """
    # 检查是否有已编译的nginx版本
    all_versions = _list_all_versions()
    compiled_versions = [v for v in all_versions if v.compiled]
    has_compiled = len(compiled_versions) > 0

    # 检查是否有默认nginx压缩包
    default_tar = _get_default_nginx_tar_path()
    has_default_tar = default_tar is not None and default_tar.exists()

    return {
        "has_compiled_nginx": has_compiled,
        "has_default_tar": has_default_tar,
        "default_version": "1.29.3" if has_default_tar else None,
    }


@router.post(
    "/setup/prepare-default",
    summary="准备默认nginx压缩包（复制到构建目录）",
)
async def prepare_default_nginx(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    将默认nginx压缩包复制到构建目录，准备编译
    """
    default_version = "1.29.3"
    default_tar = _get_default_nginx_tar_path()

    if not default_tar or not default_tar.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="默认nginx压缩包不存在",
        )

    # 检查目标文件是否已存在
    build_root = _get_build_root()
    build_root.mkdir(parents=True, exist_ok=True)
    target_tar = build_root / f"nginx-{default_version}.tar.gz"

    if target_tar.exists():
        return {
            "success": True,
            "message": f"默认压缩包已存在于构建目录",
            "version": default_version,
        }

    try:
        shutil.copy2(default_tar, target_tar)

        # 记录审计日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="nginx_setup_prepare_default",
            target=default_version,
            details={
                "source": str(default_tar),
                "target": str(target_tar),
            },
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": f"默认压缩包已复制到构建目录",
            "version": default_version,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"复制默认压缩包失败: {str(e)}",
        )
