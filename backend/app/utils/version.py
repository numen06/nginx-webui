"""
系统版本管理工具
基于编译时间生成版本号
"""
from pathlib import Path
from datetime import datetime
import os


def get_build_time_file() -> Path:
    """获取构建时间文件路径"""
    # 使用环境变量 DATA_ROOT 或默认路径
    data_root = os.getenv("DATA_ROOT", "/app/data").rstrip("/")
    build_time_file = Path(data_root) / "backend" / ".build_time"
    return build_time_file


def get_build_time() -> str:
    """
    获取系统构建时间（编译时间）
    
    Returns:
        构建时间字符串，格式：YYYYMMDDHHMMSS
    """
    build_time_file = get_build_time_file()
    
    # 如果文件存在，读取构建时间
    if build_time_file.exists():
        try:
            return build_time_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    
    # 如果文件不存在，使用当前时间（首次运行）
    # 这通常发生在开发环境或首次部署
    current_time = datetime.now().strftime("%Y%m%d%H%M%S")
    
    # 尝试保存构建时间（如果目录可写）
    try:
        build_time_file.parent.mkdir(parents=True, exist_ok=True)
        build_time_file.write_text(current_time, encoding="utf-8")
    except Exception:
        # 如果无法写入，忽略错误
        pass
    
    return current_time


def get_version() -> str:
    """
    获取系统版本号（基于构建时间）
    
    Returns:
        版本号字符串，格式：v.YYYYMMDD.HHMMSS
    """
    build_time = get_build_time()
    
    # 格式：v.YYYYMMDD.HHMMSS
    if len(build_time) >= 14:
        date_part = build_time[:8]  # YYYYMMDD
        time_part = build_time[8:14]  # HHMMSS
        return f"v.{date_part}.{time_part}"
    elif len(build_time) >= 8:
        # 只有日期部分
        return f"v.{build_time[:8]}"
    else:
        return f"v.{build_time}"


def get_version_info() -> dict:
    """
    获取完整的版本信息
    
    Returns:
        包含版本号、构建时间等信息的字典
    """
    build_time = get_build_time()
    
    # 解析构建时间
    try:
        if len(build_time) >= 14:
            build_datetime = datetime.strptime(build_time, "%Y%m%d%H%M%S")
        elif len(build_time) >= 8:
            build_datetime = datetime.strptime(build_time[:8], "%Y%m%d")
        else:
            build_datetime = None
    except Exception:
        build_datetime = None
    
    version = get_version()
    
    return {
        "version": version,
        "build_time": build_time,
        "build_datetime": build_datetime.isoformat() if build_datetime else None,
        "build_date": build_datetime.strftime("%Y-%m-%d") if build_datetime else None,
        "build_time_formatted": build_datetime.strftime("%Y-%m-%d %H:%M:%S") if build_datetime else None,
    }


def set_build_time(build_time: str = None) -> None:
    """
    设置构建时间（通常在构建时调用）
    
    Args:
        build_time: 构建时间字符串，格式：YYYYMMDDHHMMSS。如果为None，使用当前时间
    """
    if build_time is None:
        build_time = datetime.now().strftime("%Y%m%d%H%M%S")
    
    build_time_file = get_build_time_file()
    try:
        build_time_file.parent.mkdir(parents=True, exist_ok=True)
        build_time_file.write_text(build_time, encoding="utf-8")
    except Exception as e:
        # 如果无法写入，忽略错误
        print(f"无法保存构建时间: {e}")

