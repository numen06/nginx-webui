"""
Nginx 日志轮转工具
支持自动和手动日志轮转，清理旧日志文件
"""

import os
import re
import shlex
from threading import Lock
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.config import get_config, MIN_LOG_RETENTION_DAYS
from app.utils.nginx_versions import get_active_version, _find_pid_for_version

logger = logging.getLogger(__name__)
rotation_lock = Lock()


def _resolve_log_path(config_path: str) -> str:
    """
    解析日志文件路径，将相对路径转换为绝对路径。
    
    Args:
        config_path: 配置中的日志路径（可能是相对路径或绝对路径）
    
    Returns:
        解析后的绝对路径字符串
    """
    log_path = Path(config_path)
    
    # 如果已经是绝对路径，直接返回
    if log_path.is_absolute():
        return str(log_path.resolve())
    
    # 相对路径需要解析：相对于 backend 目录
    # 当前文件在 backend/app/utils/logrotate.py
    # parents[2] -> backend 目录
    backend_dir = Path(__file__).resolve().parents[2]
    resolved_path = (backend_dir / config_path).resolve()
    
    return str(resolved_path)


def _resolve_nginx_log_path(directive: str) -> str:
    """解析主配置中的本地日志文件，兼容旧版使用安装目录的默认路径。"""
    active = get_active_version()
    if active is None:
        return _resolve_log_path(getattr(get_config().nginx, directive))

    prefix = active["install_path"]
    config_path = prefix / "conf" / "nginx.conf"
    if config_path.is_file():
        content = config_path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(rf"^\s*{directive}\s+([^;]+);", content, re.MULTILINE):
            try:
                args = shlex.split(match[1])
            except ValueError:
                continue
            if args and args[0] not in {"off", "stderr"} and not args[0].startswith(("syslog:", "memory:")) and "$" not in args[0]:
                return str((prefix / args[0]).resolve())
    return str((prefix / "logs" / directive.replace("_", ".")).resolve())


def _resolve_access_log_path() -> str:
    return _resolve_nginx_log_path("access_log")


def _resolve_error_log_path() -> str:
    return _resolve_nginx_log_path("error_log")


def _get_nginx_pid() -> Optional[int]:
    """
    获取当前运行中的 Nginx 主进程 PID
    
    Returns:
        Nginx 主进程 PID，如果未找到返回 None
    """
    try:
        active = get_active_version()
        if active is not None:
            install_path = active["install_path"]
            pid = _find_pid_for_version(install_path)
            if pid:
                return pid
        
        # 如果没有活动版本，尝试通过 psutil 查找
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    if proc.info['name'] == 'nginx' or (proc.info['cmdline'] and 'nginx' in proc.info['cmdline'][0]):
                        # 检查是否是主进程（通常主进程的父进程是 init 或 systemd）
                        parent = proc.parent()
                        if parent is None or parent.pid == 1:
                            return proc.info['pid']
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except ImportError:
            pass
        
        return None
    except Exception as e:
        logger.warning(f"获取 Nginx PID 失败: {e}")
        return None


def send_nginx_reopen_signal() -> bool:
    """
    向 Nginx 发送 USR1 信号，使其重新打开日志文件
    
    Returns:
        True 表示成功发送信号，False 表示失败
    """
    pid = _get_nginx_pid()
    if pid is None:
        logger.warning("未找到运行中的 Nginx 进程，跳过信号发送")
        return False
    
    try:
        import signal
        os.kill(pid, signal.SIGUSR1)
        logger.info(f"已向 Nginx 主进程 (PID: {pid}) 发送 USR1 信号")
        return True
    except ProcessLookupError:
        logger.warning(f"Nginx 进程 (PID: {pid}) 不存在")
        return False
    except PermissionError:
        logger.error(f"没有权限向 Nginx 进程 (PID: {pid}) 发送信号")
        return False
    except Exception as e:
        logger.error(f"发送 USR1 信号失败: {e}")
        return False


def rotate_log_file(log_path: Path) -> Tuple[bool, Optional[str], Optional[str]]:
    """重命名当前文件，由 Nginx 收到 USR1 后创建并接管新文件。"""
    try:
        if log_path.stat().st_size == 0:
            return False, None, None
        now = datetime.now()
        rotated_path = log_path.with_name(f"{log_path.name}.{now:%Y-%m-%d}")
        if rotated_path.exists():
            rotated_path = log_path.with_name(f"{rotated_path.name}.{now:%Y%m%d_%H%M%S_%f}")
        log_path.rename(rotated_path)
        return True, str(rotated_path), None
    except OSError as exc:
        return False, None, f"轮转日志文件失败: {exc}"


def rotated_log_date(log_path: Path, basename: str) -> Optional[datetime]:
    prefix = f"{basename}."
    if not log_path.name.startswith(prefix) or log_path.is_symlink():
        return None
    try:
        return datetime.strptime(log_path.name[len(prefix):].split(".", 1)[0], "%Y-%m-%d")
    except ValueError:
        return None


def can_delete_rotated_log(log_path: Path, basename: str, cutoff: datetime) -> bool:
    file_date = rotated_log_date(log_path, basename)
    return (
        file_date is not None
        and file_date < cutoff
        and log_path.is_file()
        and datetime.fromtimestamp(log_path.stat().st_mtime) < cutoff
    )


def cleanup_old_logs(log_dir: Path, log_basename: str, retention_days: int) -> List[str]:
    cutoff = datetime.now() - timedelta(days=max(retention_days, MIN_LOG_RETENTION_DAYS))
    deleted = []
    for log_file in log_dir.iterdir():
        try:
            if can_delete_rotated_log(log_file, log_basename, cutoff):
                log_file.unlink()
                deleted.append(str(log_file))
        except OSError:
            logger.warning("无法清理日志分片 %s", log_file, exc_info=True)
    return deleted


def rotate_logs(retention_days: int = MIN_LOG_RETENTION_DAYS) -> Dict:
    with rotation_lock:
        return _rotate_logs(retention_days)


def _rotate_logs(retention_days: int) -> Dict:
    """
    执行日志轮转
    
    Args:
        retention_days: 日志保留天数
        
    Returns:
        轮转结果字典，包含：
        - success: 是否成功
        - rotated_files: 轮转的文件列表
        - deleted_files: 删除的文件列表
        - errors: 错误信息列表
        - nginx_signal_sent: 是否成功发送 Nginx 信号
    """
    result = {
        "success": True,
        "rotated_files": [],
        "deleted_files": [],
        "errors": [],
        "nginx_signal_sent": False,
    }
    
    try:
        # 获取日志文件路径
        access_log_path = Path(_resolve_access_log_path())
        error_log_path = Path(_resolve_error_log_path())
        
        # 轮转访问日志
        if access_log_path.exists():
            success, rotated_path, error = rotate_log_file(access_log_path)
            if success and rotated_path:
                result["rotated_files"].append({
                    "type": "access",
                    "original": str(access_log_path),
                    "rotated": rotated_path,
                })
            elif error:
                result["errors"].append(f"访问日志轮转失败: {error}")
                result["success"] = False
        
        # 轮转错误日志
        if error_log_path != access_log_path and error_log_path.exists():
            success, rotated_path, error = rotate_log_file(error_log_path)
            if success and rotated_path:
                result["rotated_files"].append({
                    "type": "error",
                    "original": str(error_log_path),
                    "rotated": rotated_path,
                })
            elif error:
                result["errors"].append(f"错误日志轮转失败: {error}")
                result["success"] = False
        
        # 若上次重开失败且当前文件缺失，下一轮继续尝试重开。
        if result["rotated_files"] or not access_log_path.exists() or not error_log_path.exists():
            result["nginx_signal_sent"] = send_nginx_reopen_signal()
            if not result["nginx_signal_sent"]:
                result["errors"].append("发送 Nginx USR1 信号失败，保留已轮转日志")
                result["success"] = False
                return result

        for log_path in dict.fromkeys((access_log_path, error_log_path)):
            if log_path.parent.is_dir():
                result["deleted_files"].extend(cleanup_old_logs(log_path.parent, log_path.name, retention_days))

        logger.info(f"日志轮转完成: 轮转 {len(result['rotated_files'])} 个文件, 删除 {len(result['deleted_files'])} 个旧文件")
        
    except Exception as e:
        error_msg = f"日志轮转过程出错: {e}"
        logger.error(error_msg, exc_info=True)
        result["success"] = False
        result["errors"].append(error_msg)
    
    return result

