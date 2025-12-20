"""
Nginx 日志轮转工具
支持自动和手动日志轮转，清理旧日志文件
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from app.config import get_config
from app.utils.nginx_versions import get_active_version, _find_pid_for_version
from app.routers.logs import _resolve_access_log_path, _resolve_error_log_path

logger = logging.getLogger(__name__)


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


def rotate_log_file(log_path: Path, retention_days: int = 7) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    轮转单个日志文件
    
    Args:
        log_path: 日志文件路径
        retention_days: 保留天数
        
    Returns:
        (成功标志, 轮转后的文件路径, 错误信息)
    """
    if not log_path.exists():
        return False, None, f"日志文件不存在: {log_path}"
    
    # 检查文件是否为空
    if log_path.stat().st_size == 0:
        logger.info(f"日志文件为空，跳过轮转: {log_path}")
        return False, None, "日志文件为空"
    
    try:
        # 生成轮转后的文件名：原文件名.YYYY-MM-DD
        today = datetime.now().strftime("%Y-%m-%d")
        rotated_path = log_path.parent / f"{log_path.name}.{today}"
        
        # 如果同一天的轮转文件已存在，添加时间戳后缀
        if rotated_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_path = log_path.parent / f"{log_path.name}.{today}.{timestamp}"
        
        # 重命名当前日志文件
        shutil.move(str(log_path), str(rotated_path))
        logger.info(f"日志文件已轮转: {log_path} -> {rotated_path}")
        
        # 创建新的空日志文件
        log_path.touch()
        # 设置与原始文件相同的权限（如果可能）
        try:
            if rotated_path.exists():
                stat_info = rotated_path.stat()
                os.chmod(log_path, stat_info.st_mode)
        except Exception:
            pass
        
        return True, str(rotated_path), None
    except Exception as e:
        error_msg = f"轮转日志文件失败: {e}"
        logger.error(error_msg)
        return False, None, error_msg


def cleanup_old_logs(log_dir: Path, log_basename: str, retention_days: int) -> List[str]:
    """
    清理超过保留天数的旧日志文件
    
    Args:
        log_dir: 日志目录
        log_basename: 日志文件基础名称（如 "access.log" 或 "error.log"）
        retention_days: 保留天数
        
    Returns:
        已删除的文件路径列表
    """
    deleted_files = []
    cutoff_date = datetime.now() - timedelta(days=retention_days)
    
    try:
        # 查找所有匹配的轮转日志文件：log_basename.YYYY-MM-DD 或 log_basename.YYYY-MM-DD.*
        pattern_prefix = f"{log_basename}."
        for log_file in log_dir.iterdir():
            if not log_file.is_file():
                continue
            
            if log_file.name.startswith(pattern_prefix):
                # 尝试从文件名中提取日期
                # 格式：log_basename.YYYY-MM-DD 或 log_basename.YYYY-MM-DD.timestamp
                parts = log_file.name[len(pattern_prefix):].split(".")
                if len(parts) >= 1:
                    date_str = parts[0]
                    try:
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        if file_date < cutoff_date:
                            try:
                                log_file.unlink()
                                deleted_files.append(str(log_file))
                                logger.info(f"已删除旧日志文件: {log_file}")
                            except Exception as e:
                                logger.warning(f"删除旧日志文件失败: {log_file}, 错误: {e}")
                    except ValueError:
                        # 无法解析日期，跳过
                        continue
    except Exception as e:
        logger.error(f"清理旧日志文件时出错: {e}")
    
    return deleted_files


def rotate_logs(retention_days: int = 7) -> Dict:
    """
    执行日志轮转
    
    Args:
        retention_days: 保留天数，默认 7 天
        
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
            success, rotated_path, error = rotate_log_file(access_log_path, retention_days)
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
        if error_log_path.exists():
            success, rotated_path, error = rotate_log_file(error_log_path, retention_days)
            if success and rotated_path:
                result["rotated_files"].append({
                    "type": "error",
                    "original": str(error_log_path),
                    "rotated": rotated_path,
                })
            elif error:
                result["errors"].append(f"错误日志轮转失败: {error}")
                result["success"] = False
        
        # 如果至少有一个日志文件轮转成功，发送 Nginx 信号
        if result["rotated_files"]:
            nginx_signal_sent = send_nginx_reopen_signal()
            result["nginx_signal_sent"] = nginx_signal_sent
            if not nginx_signal_sent:
                result["errors"].append("发送 Nginx USR1 信号失败，但日志已轮转")
        
        # 清理旧日志文件
        if access_log_path.exists():
            log_dir = access_log_path.parent
            deleted = cleanup_old_logs(log_dir, access_log_path.name, retention_days)
            result["deleted_files"].extend(deleted)
        
        if error_log_path.exists():
            log_dir = error_log_path.parent
            deleted = cleanup_old_logs(log_dir, error_log_path.name, retention_days)
            result["deleted_files"].extend(deleted)
        
        logger.info(f"日志轮转完成: 轮转 {len(result['rotated_files'])} 个文件, 删除 {len(result['deleted_files'])} 个旧文件")
        
    except Exception as e:
        error_msg = f"日志轮转过程出错: {e}"
        logger.error(error_msg, exc_info=True)
        result["success"] = False
        result["errors"].append(error_msg)
    
    return result

