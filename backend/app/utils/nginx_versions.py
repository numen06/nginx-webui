"""
Nginx 多版本辅助工具

用于在不依赖路由层的情况下，检测当前通过源码编译安装的
Nginx 版本及其运行状态，供配置管理、日志管理等模块使用。
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

from app.config import get_config

_VERSION_METADATA_FILENAME = ".nginx-version"


def _get_versions_root() -> Path:
    """
    获取 Nginx 多版本安装根目录（绝对路径）

    - 如果配置中是绝对路径，则直接返回
    - 如果是相对路径，则相对于 backend 目录解析
    """
    config = get_config()
    raw = Path(config.nginx.versions_root)
    if raw.is_absolute():
        return raw

    # 当前文件在 backend/app/utils/nginx_versions.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    return (backend_dir / raw).resolve()


def _get_install_path(version: str) -> Path:
    """根据版本号获取安装路径"""
    return _get_versions_root() / version


def _get_pid_file(install_path: Path) -> Path:
    """
    获取指定安装目录下的 PID 文件路径

    按照编译时 --prefix=<install_path> 的约定：
    PID 位于 <install_path>/logs/nginx.pid
    """
    return install_path / "logs" / "nginx.pid"


def _check_process_running(pid: int) -> bool:
    """检查指定 PID 的进程是否仍在运行"""
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _get_version_metadata_path(install_path: Path) -> Path:
    """返回版本元数据文件路径"""
    return install_path / _VERSION_METADATA_FILENAME


def _detect_nginx_binary_version(executable: Path) -> Optional[str]:
    """执行 nginx -v 解析实际版本号"""
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


def _resolve_version_label(directory: str, install_path: Path) -> Optional[str]:
    """
    解析目录对应的版本号。

    优先顺序：
    1. 目录内的元数据文件
    2. 对于非 last 目录，直接使用目录名称
    3. 对于 last 目录，如果未记录元数据，则尝试通过可执行文件检测
    """
    meta_path = _get_version_metadata_path(install_path)
    if meta_path.exists():
        try:
            content = meta_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass

    if directory != "last":
        return directory

    executable = install_path / "sbin" / "nginx"
    return _detect_nginx_binary_version(executable)


def get_active_version() -> Optional[Dict[str, Any]]:
    """
    检测当前“活动”的 Nginx 版本。

    约定：
    - 通过多版本管理编译安装的 Nginx 会在 <versions_root>/<version> 下生成安装目录
    - 每个安装目录下的 PID 文件为 logs/nginx.pid
    - 认为“活动版本” = PID 文件存在且对应进程仍在运行的版本

    Returns:
        None: 未找到运行中的版本
        dict: {
            "directory": str,
            "version": str,
            "install_path": Path,
            "executable": Path,
        }
    """
    versions_root = _get_versions_root()
    if not versions_root.exists():
        return None

    active: Optional[Dict[str, Any]] = None

    for child in sorted(versions_root.iterdir()):
        if not child.is_dir():
            continue

        install_path = _get_install_path(child.name)
        pid_file = _get_pid_file(install_path)

        if not pid_file.exists():
            continue

        try:
            content = pid_file.read_text(encoding="utf-8").strip()
            if not content:
                continue
            pid = int(content)
        except Exception:
            continue

        if not _check_process_running(pid):
            continue

        # 找到一个运行中的版本，即视为当前活动版本
        executable = install_path / "sbin" / "nginx"
        resolved_version = _resolve_version_label(child.name, install_path) or child.name
        active = {
            "directory": child.name,
            "version": resolved_version,
            "install_path": install_path,
            "executable": executable,
        }
        # 按名称排序后的第一个运行中的版本，直接返回
        break

    return active


