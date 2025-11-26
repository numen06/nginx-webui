"""
Nginx 操作工具
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from app.config import get_config


def get_config_content() -> str:
    """读取 Nginx 配置文件内容"""
    config = get_config()
    config_path = Path(config.nginx.config_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Nginx 配置文件不存在: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        return f.read()


def save_config_content(content: str) -> bool:
    """保存 Nginx 配置文件"""
    config = get_config()
    config_path = Path(config.nginx.config_path)
    
    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
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
    config = get_config()
    nginx_executable = Path(config.nginx.executable)
    
    if not nginx_executable.exists():
        return {
            "success": False,
            "message": f"Nginx 可执行文件不存在: {nginx_executable}",
            "output": ""
        }
    
    try:
        result = subprocess.run(
            [str(nginx_executable), "-t"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        success = result.returncode == 0
        
        return {
            "success": success,
            "message": "配置测试成功" if success else "配置测试失败",
            "output": result.stdout + result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "配置测试超时",
            "output": ""
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"配置测试出错: {str(e)}",
            "output": ""
        }


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
    config = get_config()
    nginx_executable = Path(config.nginx.executable)
    
    if not nginx_executable.exists():
        return {
            "success": False,
            "message": f"Nginx 可执行文件不存在: {nginx_executable}",
            "output": ""
        }
    
    try:
        result = subprocess.run(
            [str(nginx_executable), "-s", "reload"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        success = result.returncode == 0
        
        return {
            "success": success,
            "message": "配置重载成功" if success else "配置重载失败",
            "output": result.stdout + result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "配置重载超时",
            "output": ""
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"配置重载出错: {str(e)}",
            "output": ""
        }


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
    nginx_executable = Path(config.nginx.executable)
    
    if not nginx_executable.exists():
        return {
            "running": False,
            "pid": None,
            "version": None
        }
    
    try:
        # 检查进程是否运行
        result = subprocess.run(
            ["pgrep", "-f", "nginx"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        running = result.returncode == 0
        pid = None
        if running and result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            pid = int(pids[0]) if pids else None
        
        # 获取版本信息
        version_result = subprocess.run(
            [str(nginx_executable), "-v"],
            capture_output=True,
            text=True,
            timeout=5
        )
        version = version_result.stderr.strip() if version_result.stderr else None
        
        return {
            "running": running,
            "pid": pid,
            "version": version
        }
    except Exception as e:
        return {
            "running": False,
            "pid": None,
            "version": None,
            "error": str(e)
        }

