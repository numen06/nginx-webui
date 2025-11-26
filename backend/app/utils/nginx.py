"""
Nginx 操作工具
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

from app.config import get_config
from app.utils.nginx_versions import get_active_version


def _resolve_nginx_executable() -> Path:
    """
    解析当前应当使用的 Nginx 可执行文件路径。

    优先级：
    1. 如果通过源码包编译的多版本 Nginx 中存在“正在运行”的版本，
       则认为该版本为当前活动版本，使用其 sbin/nginx。
    2. 否则回退到配置文件中的 nginx.executable。
    """
    config = get_config()

    active = get_active_version()
    if active is not None:
        return active["executable"]

    return Path(config.nginx.executable)


def get_config_path() -> Path:
    """
    获取当前使用的 Nginx 配置文件路径

    Returns:
        配置文件路径
    """
    config = get_config()

    # 如果存在通过多版本管理启动的"活动版本"，
    # 则优先使用该版本下的 conf/nginx.conf 作为配置文件。
    active = get_active_version()
    if active is not None:
        config_path = active["install_path"] / "conf" / "nginx.conf"
    else:
        config_path = Path(config.nginx.config_path)
        # 如果是相对路径，需要解析为绝对路径
        if not config_path.is_absolute():
            # 相对于 backend 目录解析
            backend_dir = Path(__file__).resolve().parents[2]
            config_path = (backend_dir / config_path).resolve()

    return config_path


def get_config_content() -> str:
    """读取 Nginx 配置文件内容"""
    config_path = get_config_path()

    if not config_path.exists():
        raise FileNotFoundError(f"Nginx 配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return f.read()


def save_config_content(content: str) -> bool:
    """保存 Nginx 配置文件"""
    config_path = get_config_path()

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def test_config() -> Dict[str, Any]:
    """
    测试 Nginx 配置有效性

    Returns:
        {
            "success": bool,
            "message": str,
            "output": str
        }
    """
    nginx_executable = _resolve_nginx_executable()

    if not nginx_executable.exists():
        return {
            "success": False,
            "message": f"Nginx 可执行文件不存在: {nginx_executable}",
            "output": "",
        }

    try:
        result = subprocess.run(
            [str(nginx_executable), "-t"], capture_output=True, text=True, timeout=10
        )

        success = result.returncode == 0

        return {
            "success": success,
            "message": "配置测试成功" if success else "配置测试失败",
            "output": result.stdout + result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "配置测试超时", "output": ""}
    except Exception as e:
        return {"success": False, "message": f"配置测试出错: {str(e)}", "output": ""}


def reload_nginx() -> Dict[str, Any]:
    """
    重新加载 Nginx 配置

    Returns:
        {
            "success": bool,
            "message": str,
            "output": str
        }
    """
    nginx_executable = _resolve_nginx_executable()

    if not nginx_executable.exists():
        return {
            "success": False,
            "message": f"Nginx 可执行文件不存在: {nginx_executable}",
            "output": "",
        }

    try:
        result = subprocess.run(
            [str(nginx_executable), "-s", "reload"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        success = result.returncode == 0

        return {
            "success": success,
            "message": "配置重载成功" if success else "配置重载失败",
            "output": result.stdout + result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "message": "配置重载超时", "output": ""}
    except Exception as e:
        return {"success": False, "message": f"配置重载出错: {str(e)}", "output": ""}


def get_nginx_status() -> Dict[str, Any]:
    """
    获取 Nginx 运行状态

    Returns:
        {
            "running": bool,
            "pid": Optional[int],
            "version": Optional[str]
        }
    """
    config = get_config()
    nginx_executable = _resolve_nginx_executable()
    active = get_active_version()

    if not nginx_executable.exists():
        info: Dict[str, Any] = {"running": False, "pid": None, "version": None}
        if active is not None:
            info["active_version"] = active["version"]
            info["install_path"] = str(active["install_path"])
            info["binary"] = str(active["executable"])
        return info

    try:
        # 检查进程是否运行
        result = subprocess.run(
            ["pgrep", "-f", "nginx"], capture_output=True, text=True, timeout=5
        )

        running = result.returncode == 0
        pid = None
        if running and result.stdout.strip():
            pids = result.stdout.strip().split("\n")
            pid = int(pids[0]) if pids else None

        # 获取版本信息（来自 nginx 可执行文件本身）
        version_result = subprocess.run(
            [str(nginx_executable), "-v"], capture_output=True, text=True, timeout=5
        )
        version = version_result.stderr.strip() if version_result.stderr else None

        info: Dict[str, Any] = {"running": running, "pid": pid, "version": version}
        # 如果是通过多版本管理启动的 Nginx，可以补充当前活动版本号及安装路径
        if active is not None:
            info["active_version"] = active["version"]
            info["install_path"] = str(active["install_path"])
            info["binary"] = str(active["executable"])

        return info
    except Exception as e:
        return {"running": False, "pid": None, "version": None, "error": str(e)}
