"""
系统资源监控路由
提供CPU、内存、磁盘等系统资源信息
"""
import platform
import shutil
from typing import Dict, Any
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth import get_current_user, User

router = APIRouter(prefix="/api/system", tags=["system"])


def get_cpu_info() -> Dict[str, Any]:
    """获取CPU使用率信息"""
    try:
        import psutil
        
        # CPU使用率（1秒间隔）
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # 每个CPU核心的使用率
        cpu_per_core = psutil.cpu_percent(interval=1, percpu=True)
        
        # CPU频率
        cpu_freq = psutil.cpu_freq()
        cpu_freq_info = {
            "current": round(cpu_freq.current, 2) if cpu_freq else None,
            "min": round(cpu_freq.min, 2) if cpu_freq and cpu_freq.min else None,
            "max": round(cpu_freq.max, 2) if cpu_freq and cpu_freq.max else None,
        }
        
        # CPU数量
        cpu_count = {
            "physical": psutil.cpu_count(logical=False),
            "logical": psutil.cpu_count(logical=True)
        }
        
        # CPU时间统计
        cpu_times = psutil.cpu_times()
        
        return {
            "percent": round(cpu_percent, 2),
            "per_core": [round(c, 2) for c in cpu_per_core],
            "frequency": cpu_freq_info,
            "count": cpu_count,
            "times": {
                "user": round(cpu_times.user, 2),
                "system": round(cpu_times.system, 2),
                "idle": round(cpu_times.idle, 2),
                "iowait": round(getattr(cpu_times, 'iowait', 0), 2),
            }
        }
    except ImportError:
        return {
            "percent": 0,
            "per_core": [],
            "frequency": {"current": None, "min": None, "max": None},
            "count": {"physical": 0, "logical": 0},
            "times": {"user": 0, "system": 0, "idle": 0, "iowait": 0},
            "error": "psutil未安装"
        }
    except Exception as e:
        return {
            "error": f"获取CPU信息失败: {str(e)}"
        }


def get_memory_info() -> Dict[str, Any]:
    """获取内存使用信息"""
    try:
        import psutil
        
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "free": memory.free,
            "percent": round(memory.percent, 2),
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "free": swap.free,
                "percent": round(swap.percent, 2),
            }
        }
    except ImportError:
        return {
            "total": 0,
            "available": 0,
            "used": 0,
            "free": 0,
            "percent": 0,
            "swap": {"total": 0, "used": 0, "free": 0, "percent": 0},
            "error": "psutil未安装"
        }
    except Exception as e:
        return {
            "error": f"获取内存信息失败: {str(e)}"
        }


def get_disk_info() -> Dict[str, Any]:
    """获取磁盘使用信息"""
    try:
        import psutil
        
        disk_usage = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()
        
        # 获取所有磁盘分区
        partitions = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                partitions.append({
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "fstype": partition.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": round(usage.percent, 2)
                })
            except PermissionError:
                # 某些分区可能没有权限访问
                continue
        
        return {
            "root": {
                "total": disk_usage.total,
                "used": disk_usage.used,
                "free": disk_usage.free,
                "percent": round(disk_usage.percent, 2),
            },
            "partitions": partitions,
            "io": {
                "read_count": disk_io.read_count if disk_io else 0,
                "write_count": disk_io.write_count if disk_io else 0,
                "read_bytes": disk_io.read_bytes if disk_io else 0,
                "write_bytes": disk_io.write_bytes if disk_io else 0,
            } if disk_io else {}
        }
    except ImportError:
        # 如果没有psutil，尝试使用shutil（只能获取根分区）
        try:
            disk_usage = shutil.disk_usage('/')
            return {
                "root": {
                    "total": disk_usage.total,
                    "used": disk_usage.used,
                    "free": disk_usage.free,
                    "percent": round((disk_usage.used / disk_usage.total) * 100, 2),
                },
                "partitions": [],
                "io": {},
                "warning": "仅显示根分区信息"
            }
        except Exception as e:
            return {
                "error": f"获取磁盘信息失败: {str(e)}"
            }
    except Exception as e:
        return {
            "error": f"获取磁盘信息失败: {str(e)}"
        }


def get_network_info() -> Dict[str, Any]:
    """获取网络信息"""
    try:
        import psutil
        
        net_io = psutil.net_io_counters()
        net_connections = len(psutil.net_connections(kind='inet'))
        
        # 网络接口信息
        net_if_addrs = psutil.net_if_addrs()
        interfaces = []
        for interface_name, interface_addresses in net_if_addrs.items():
            for address in interface_addresses:
                if address.family == 2:  # IPv4
                    interfaces.append({
                        "name": interface_name,
                        "address": address.address,
                        "netmask": address.netmask,
                    })
        
        return {
            "bytes_sent": net_io.bytes_sent if net_io else 0,
            "bytes_recv": net_io.bytes_recv if net_io else 0,
            "packets_sent": net_io.packets_sent if net_io else 0,
            "packets_recv": net_io.packets_recv if net_io else 0,
            "connections": net_connections,
            "interfaces": interfaces[:10]  # 最多返回10个接口
        }
    except ImportError:
        return {
            "bytes_sent": 0,
            "bytes_recv": 0,
            "packets_sent": 0,
            "packets_recv": 0,
            "connections": 0,
            "interfaces": [],
            "error": "psutil未安装"
        }
    except Exception as e:
        return {
            "error": f"获取网络信息失败: {str(e)}"
        }


def get_system_info() -> Dict[str, Any]:
    """获取系统基本信息"""
    try:
        import psutil
        import time
        
        boot_time = psutil.boot_time()
        uptime_seconds = int(time.time() - boot_time)
        
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "boot_time": boot_time,
            "uptime_seconds": uptime_seconds,
        }
    except ImportError:
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "boot_time": None,
            "uptime_seconds": None,
            "warning": "部分信息需要psutil"
        }
    except Exception as e:
        return {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "error": f"获取系统信息失败: {str(e)}"
        }


@router.get("/resources", summary="获取系统资源信息")
async def get_system_resources(
    current_user: User = Depends(get_current_user)
):
    """获取CPU、内存、磁盘、网络等系统资源信息"""
    try:
        return {
            "success": True,
            "cpu": get_cpu_info(),
            "memory": get_memory_info(),
            "disk": get_disk_info(),
            "network": get_network_info(),
            "system": get_system_info(),
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取系统资源信息失败: {str(e)}"
        )

