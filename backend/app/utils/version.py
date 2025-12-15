"""
系统版本管理工具

- APP 版本号：表示当前程序版本，例如 1.0.0（来自环境变量或默认值）
- 构建时间：镜像 / 程序的构建时间，用于辅助排查问题
"""

from pathlib import Path
from datetime import datetime
import os

from app.config import get_config

# 当前程序版本号（系统版本）
# 优先使用配置文件中的 app.version，其次使用环境变量 APP_VERSION，最后使用默认值
DEFAULT_VERSION = "1.0.1"


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
    获取系统版本号（当前程序版本，而不是 Nginx 编译时间）

    Returns:
        版本号字符串，例如：1.0.1
    """
    # 1) 优先从配置文件读取（config.yaml -> app.version）
    try:
        config = get_config()
        app_version = getattr(getattr(config, "app", None), "version", None)
        if isinstance(app_version, str) and app_version.strip():
            return app_version.strip()
    except Exception:
        # 配置读取异常时静默降级
        pass

    # 2) 其次使用环境变量 APP_VERSION（便于 CI/CD 注入）
    env_version = os.getenv("APP_VERSION")
    if env_version:
        return env_version

    # 3) 最后使用默认版本
    return DEFAULT_VERSION


def get_version_info() -> dict:
    """
    获取完整的版本信息

    Returns:
        包含版本号、构建时间等信息的字典
    """
    build_time = get_build_time()

    # 解析构建时间（用于展示构建时间信息，方便排查问题）
    try:
        if len(build_time) >= 14:
            build_datetime = datetime.strptime(build_time, "%Y%m%d%H%M%S")
        elif len(build_time) >= 8:
            build_datetime = datetime.strptime(build_time[:8], "%Y%m%d")
        else:
            build_datetime = None
    except Exception:
        build_datetime = None

    # 系统版本 = 当前程序版本
    version = get_version()

    return {
        # 对外统一使用 version 作为“系统版本”（当前程序版本）
        "version": version,
        "app_version": version,
        # 构建相关信息仅用于辅助展示 / 排查
        "build_time": build_time,
        "build_datetime": build_datetime.isoformat() if build_datetime else None,
        "build_date": build_datetime.strftime("%Y-%m-%d") if build_datetime else None,
        "build_time_formatted": (
            build_datetime.strftime("%Y-%m-%d %H:%M:%S") if build_datetime else None
        ),
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
