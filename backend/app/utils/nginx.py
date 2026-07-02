"""
Nginx 操作工具
"""

import fnmatch
import os
import re
import shutil
import tempfile
import zipfile
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None

from app.config import get_config
from app.utils.nginx_versions import get_active_version


def _resolve_nginx_executable() -> Optional[Path]:
    """
    解析当前应当使用的 Nginx 可执行文件路径。

    优先级：
    1. 如果通过源码包编译的多版本 Nginx 中存在"正在运行"的版本，
       则认为该版本为当前活动版本，使用其 sbin/nginx。
    2. 否则回退到配置文件中的 nginx.executable。

    Returns:
        Path: Nginx 可执行文件路径，如果不存在则返回 None
    """
    config = get_config()

    active = get_active_version()
    if active is not None:
        executable = active["executable"]
        if executable.exists():
            return executable
        return None

    executable = Path(config.nginx.executable)
    if executable.exists():
        return executable

    return None


def is_nginx_available() -> bool:
    """
    检查 Nginx 是否可用（可执行文件存在）

    Returns:
        bool: True 表示 Nginx 可用，False 表示不可用
    """
    executable = _resolve_nginx_executable()
    return executable is not None and executable.exists()


def get_nginx_executable_or_raise() -> Path:
    """
    获取 Nginx 可执行文件路径，如果不存在则抛出异常

    Returns:
        Path: Nginx 可执行文件路径

    Raises:
        FileNotFoundError: 当 Nginx 可执行文件不存在时
    """
    executable = _resolve_nginx_executable()
    if executable is None or not executable.exists():
        config = get_config()
        raise FileNotFoundError(
            f"Nginx 可执行文件不存在。请确保：\n"
            f"1. 系统已安装 Nginx，或\n"
            f"2. 已通过系统下载编译 Nginx 版本，或\n"
            f"3. 在配置文件中正确设置了 nginx.executable 路径（当前配置: {config.nginx.executable}）"
        )
    return executable


def get_config_path() -> Path:
    """
    获取当前使用的 Nginx 配置文件路径
    现在全部使用下载编译版本的配置，不再使用独立的 nginx 目录

    Returns:
        配置文件路径

    Raises:
        FileNotFoundError: 如果没有活动版本的 Nginx
    """
    # 优先使用活动版本的配置
    active = get_active_version()
    if active is not None:
        config_path = active["install_path"] / "conf" / "nginx.conf"
        if config_path.exists():
            return config_path
        # 如果配置文件不存在，尝试创建默认配置
        config_path.parent.mkdir(parents=True, exist_ok=True)
        _create_default_config_for_version(active["install_path"])
        return config_path

    # 如果没有活动版本，尝试查找任何已编译的版本
    config = get_config()
    versions_root = Path(config.nginx.versions_root)
    if not versions_root.is_absolute():
        backend_dir = Path(__file__).resolve().parents[2]
        versions_root = (backend_dir / versions_root).resolve()

    if versions_root.exists():
        # 查找最新的已编译版本
        for version_dir in sorted(
            versions_root.iterdir(), key=lambda x: x.name, reverse=True
        ):
            if version_dir.is_dir():
                config_path = version_dir / "conf" / "nginx.conf"
                if config_path.exists():
                    return config_path
                # 如果有可执行文件，创建默认配置
                executable = version_dir / "sbin" / "nginx"
                if executable.exists():
                    _create_default_config_for_version(version_dir)
                    return config_path

    # 如果都没有，抛出异常
    raise FileNotFoundError(
        "未找到可用的 Nginx 版本配置。请先下载并编译一个 Nginx 版本，或启动一个 Nginx 实例。"
    )


_WORKING_CONFIG_SUFFIX = ".webui.pending"
_WORKING_DIR_NAME = ".webui"
_PENDING_CONF_DIR_NAME = "pending-conf"
_CONFIG_EXCLUDE_PATTERNS = (
    "*.webui.pending",
    "*.tmp",
    ".DS_Store",
)


def get_config_dir() -> Path:
    """获取当前活动 Nginx 的配置目录。"""
    config_dir = get_config_path().parent
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def _get_install_path_for_config(config_path: Optional[Path] = None) -> Path:
    """根据配置文件路径推断 Nginx 安装根目录。"""
    active = get_active_version()
    if active is not None:
        return active["install_path"]

    path = config_path or get_config_path()
    if path.parent.name == "conf":
        return path.parent.parent
    return path.parent


def get_working_config_dir() -> Path:
    """获取配置目录级工作副本路径。"""
    install_path = _get_install_path_for_config()
    working_dir = install_path / _WORKING_DIR_NAME / _PENDING_CONF_DIR_NAME
    working_dir.mkdir(parents=True, exist_ok=True)
    return working_dir


def _should_skip_config_item(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in _CONFIG_EXCLUDE_PATTERNS)


def _copy_config_dir(source: Path, target: Path) -> None:
    """镜像复制配置目录，跳过 WebUI 自己的临时文件。"""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        if _should_skip_config_item(item):
            continue
        dest = target / item.name
        if item.is_dir():
            shutil.copytree(
                item,
                dest,
                ignore=shutil.ignore_patterns(*_CONFIG_EXCLUDE_PATTERNS),
            )
        else:
            shutil.copy2(item, dest)


def ensure_working_config_dir(sync_from_actual: bool = False) -> Path:
    """确保目录级工作副本存在。"""
    actual_dir = get_config_dir()
    working_dir = get_working_config_dir()
    working_main = working_dir / "nginx.conf"

    if sync_from_actual or not working_main.exists():
        _copy_config_dir(actual_dir, working_dir)

    return working_dir


def sync_working_config_dir_from_actual() -> Path:
    return ensure_working_config_dir(sync_from_actual=True)


def _relative_config_path(path: str) -> Path:
    value = (path or "").strip().replace("\\", "/").strip("/")
    if not value:
        raise ValueError("路径不能为空")
    candidate = Path(value)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise ValueError("无效的配置路径")
    return candidate


def resolve_working_config_path(path: str, must_exist: bool = False) -> Path:
    """解析工作副本内的相对配置路径。"""
    working_dir = ensure_working_config_dir()
    relative = _relative_config_path(path)
    target = (working_dir / relative).resolve()

    try:
        target.relative_to(working_dir.resolve())
    except ValueError as exc:
        raise ValueError("路径超出配置目录") from exc

    if must_exist and not target.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    return target


def _file_info(path: Path, root: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path.relative_to(root)).replace("\\", "/"),
        "is_dir": path.is_dir(),
        "size": stat.st_size if path.is_file() else 0,
        "modified_time": stat.st_mtime,
    }


def list_working_config_files() -> List[Dict[str, Any]]:
    """递归列出工作副本配置文件树。"""
    root = ensure_working_config_dir()
    entries: List[Dict[str, Any]] = []
    for item in root.rglob("*"):
        if _should_skip_config_item(item):
            continue
        entries.append(_file_info(item, root))
    entries.sort(key=lambda item: (item["path"].count("/"), not item["is_dir"], item["path"]))
    return entries


def read_working_config_file(path: str) -> Dict[str, Any]:
    target = resolve_working_config_path(path, must_exist=True)
    if target.is_dir():
        raise IsADirectoryError("指定路径是目录")
    return {
        "path": str(target.relative_to(ensure_working_config_dir())).replace("\\", "/"),
        "content": target.read_text(encoding="utf-8", errors="ignore"),
    }


def write_working_config_file(path: str, content: str, create: bool = True) -> Dict[str, Any]:
    target = resolve_working_config_path(path)
    if target.exists() and target.is_dir():
        raise IsADirectoryError("指定路径是目录")
    if not create and not target.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return read_working_config_file(path)


def create_working_config_directory(path: Optional[str], name: str) -> Dict[str, Any]:
    parent = ensure_working_config_dir()
    if path:
        parent = resolve_working_config_path(path)
    if not parent.exists() or not parent.is_dir():
        raise FileNotFoundError("父目录不存在")
    if "/" in name or "\\" in name or name in ("", ".", ".."):
        raise ValueError("无效的目录名称")
    target = parent / name
    target_resolved = target.resolve()
    target_resolved.relative_to(ensure_working_config_dir().resolve())
    if target.exists():
        raise FileExistsError("目录已存在")
    target.mkdir(parents=True)
    return _file_info(target, ensure_working_config_dir())


def rename_working_config_path(path: str, new_name: str) -> Dict[str, Any]:
    target = resolve_working_config_path(path, must_exist=True)
    if "/" in new_name or "\\" in new_name or new_name in ("", ".", ".."):
        raise ValueError("无效的新名称")
    if target.name == "nginx.conf":
        raise ValueError("不能重命名主配置文件 nginx.conf")
    new_target = target.parent / new_name
    new_target.resolve().relative_to(ensure_working_config_dir().resolve())
    if new_target.exists():
        raise FileExistsError("目标名称已存在")
    target.rename(new_target)
    return _file_info(new_target, ensure_working_config_dir())


def delete_working_config_path(path: str) -> bool:
    target = resolve_working_config_path(path, must_exist=True)
    if target.name == "nginx.conf" and target.parent == ensure_working_config_dir():
        raise ValueError("不能删除主配置文件 nginx.conf")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return True


def _iter_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(
        [p for p in root.rglob("*") if p.is_file() and not _should_skip_config_item(p)],
        key=lambda p: str(p.relative_to(root)).replace("\\", "/"),
    )


def _files_equal(left: Path, right: Path) -> bool:
    left_files = _iter_files(left)
    right_files = _iter_files(right)
    left_rel = [str(p.relative_to(left)).replace("\\", "/") for p in left_files]
    right_rel = [str(p.relative_to(right)).replace("\\", "/") for p in right_files]
    if left_rel != right_rel:
        return False

    for left_path in left_files:
        rel = left_path.relative_to(left)
        right_path = right / rel
        if left_path.read_bytes() != right_path.read_bytes():
            return False
    return True


def _resolve_include_paths_for_test(content: str, conf_dir: Path) -> str:
    """将测试配置中的相对 include 指向指定配置目录。"""
    include_pattern = re.compile(r"^(\s*)include\s+([^;]+);\s*(.*)$")
    resolved_lines = []

    for line in content.split("\n"):
        match = include_pattern.match(line)
        if not match:
            resolved_lines.append(line)
            continue

        include_path = match.group(2).strip().strip('"').strip("'")
        if os.path.isabs(include_path):
            resolved_lines.append(line)
            continue

        abs_path = conf_dir / include_path
        abs_path_str = str(abs_path)
        if '"' in match.group(2) or "'" in match.group(2):
            abs_path_str = f'"{abs_path_str}"'
        resolved_line = f"{match.group(1)}include {abs_path_str};"
        if match.group(3):
            resolved_line += f" {match.group(3)}"
        resolved_lines.append(resolved_line)

    return "\n".join(resolved_lines)


def _prepare_test_main_config(conf_dir: Path) -> Path:
    """创建一个 include 指向 conf_dir 的临时主配置文件用于 nginx -t。"""
    main_config = conf_dir / "nginx.conf"
    content = main_config.read_text(encoding="utf-8")
    resolved_content = _resolve_include_paths_for_test(content, conf_dir)
    temp = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".conf",
        delete=False,
        encoding="utf-8",
    )
    with temp:
        temp.write(resolved_content)
    return Path(temp.name)


def _run_nginx_config_test(conf_dir: Path) -> Dict[str, Any]:
    temp_main_config: Optional[Path] = None
    try:
        nginx_executable = get_nginx_executable_or_raise()
    except FileNotFoundError as e:
        return {
            "success": False,
            "message": str(e),
            "output": "",
            "errors": [str(e)],
            "warnings": [],
        }

    try:
        temp_main_config = _prepare_test_main_config(conf_dir)
        install_path = _get_install_path_for_config(get_config_path())
        cmd = [str(nginx_executable), "-t", "-c", str(temp_main_config), "-p", str(install_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return _parse_nginx_test_result(result.returncode, result.stdout + result.stderr, "配置测试")
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "配置测试超时（超过 10 秒）",
            "output": "",
            "errors": ["配置测试超时：测试过程超过 10 秒，可能配置文件过大或系统负载过高"],
            "warnings": [],
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"配置测试出错: {str(e)}",
            "output": "",
            "errors": [f"配置测试过程出错: {str(e)}"],
            "warnings": [],
        }
    finally:
        if temp_main_config and temp_main_config.exists():
            try:
                temp_main_config.unlink()
            except Exception:
                pass


def _parse_nginx_test_result(returncode: int, output: str, action_label: str) -> Dict[str, Any]:
    success = returncode == 0
    errors = []
    warnings = []

    error_pattern = re.compile(
        r'nginx:\s*\[(emerg|alert|crit|error)\]\s*(.+?)(?:\s+in\s+(.+?):(\d+))?',
        re.IGNORECASE,
    )
    warn_pattern = re.compile(
        r'nginx:\s*\[warn\]\s*(.+?)(?:\s+in\s+(.+?):(\d+))?',
        re.IGNORECASE,
    )
    test_failed_pattern = re.compile(
        r'nginx:\s*configuration\s+file\s+(.+?)\s+test\s+failed',
        re.IGNORECASE,
    )

    for line in output.split("\n"):
        line = line.strip()
        if not line:
            continue

        error_match = error_pattern.search(line)
        if error_match:
            error_level = error_match.group(1).upper()
            error_msg = error_match.group(2).strip()
            file_path = error_match.group(3) if error_match.group(3) else None
            line_num = error_match.group(4) if error_match.group(4) else None
            error_detail = f"[{error_level}] {error_msg}"
            if file_path and line_num:
                error_detail += f"\n  位置: {file_path} 第 {line_num} 行"
            elif file_path:
                error_detail += f"\n  文件: {file_path}"
            errors.append(error_detail)
            continue

        warn_match = warn_pattern.search(line)
        if warn_match:
            warn_msg = warn_match.group(1).strip()
            file_path = warn_match.group(2) if warn_match.group(2) else None
            line_num = warn_match.group(3) if warn_match.group(3) else None
            warn_detail = f"警告: {warn_msg}"
            if file_path and line_num:
                warn_detail += f"\n  位置: {file_path} 第 {line_num} 行"
            elif file_path:
                warn_detail += f"\n  文件: {file_path}"
            warnings.append(warn_detail)
            continue

        failed_match = test_failed_pattern.search(line)
        if failed_match:
            errors.append(f"配置文件测试失败: {failed_match.group(1)}")
            continue

        if "error" in line.lower() or "failed" in line.lower():
            if line not in errors:
                errors.append(line)
        elif "warn" in line.lower() or "warning" in line.lower():
            if line not in warnings:
                warnings.append(line)

    if success:
        message = f"{action_label}成功"
        if warnings:
            message += f"，但有 {len(warnings)} 个警告"
    elif errors:
        error_count = len(errors)
        message = f"{action_label}失败，发现 {error_count} 个错误"
        if error_count == 1:
            message += f": {errors[0].split(chr(10))[0][:100]}"
    else:
        message = f"{action_label}失败"

    return {
        "success": success,
        "message": message,
        "output": output,
        "errors": errors,
        "warnings": warnings,
    }


def _working_config_path_for(config_path: Path) -> Path:
    return get_working_config_dir() / config_path.name


def get_working_config_path() -> Path:
    return ensure_working_config_dir() / "nginx.conf"


def ensure_working_config(sync_from_actual: bool = False) -> Path:
    return ensure_working_config_dir(sync_from_actual=sync_from_actual) / "nginx.conf"


def sync_working_config_from_actual() -> Path:
    sync_working_config_dir_from_actual()
    return get_working_config_path()


def has_pending_config_changes() -> bool:
    try:
        return not _files_equal(get_config_dir(), ensure_working_config_dir())
    except Exception:
        return True


def apply_working_config() -> Path:
    working_dir = ensure_working_config_dir()
    actual_dir = get_config_dir()
    _copy_config_dir(working_dir, actual_dir)
    return actual_dir / "nginx.conf"


def _create_default_config_for_version(install_path: Path) -> None:
    """
    为指定版本的 Nginx 创建默认配置文件

    Args:
        install_path: Nginx 版本的安装目录路径
    """
    config = get_config()
    config_path = install_path / "conf" / "nginx.conf"

    # 如果配置文件已存在，不创建
    if config_path.exists():
        return

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # 使用版本目录下的 conf.d，如果不存在则创建
    conf_d_dir = install_path / "conf" / "conf.d"
    conf_d_dir.mkdir(parents=True, exist_ok=True)

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

    # 确保日志目录存在
    log_dir.mkdir(parents=True, exist_ok=True)

    # 创建默认的 nginx.conf，使用版本目录下的 conf.d
    default_nginx_conf = f"""#user  nobody;
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

    # 使用版本目录下的 conf.d 配置
    include conf.d/*.conf;
}}
"""

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(default_nginx_conf)

    # 创建默认的 conf.d/default.conf
    default_conf_path = conf_d_dir / "default.conf"
    if not default_conf_path.exists():
        # 使用版本目录下的 html 目录作为静态文件目录
        html_dir = install_path / "html"
        html_dir.mkdir(parents=True, exist_ok=True)

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
        with open(default_conf_path, "w", encoding="utf-8") as f:
            f.write(default_server_conf)

        # 如果 html 目录下没有 index.html，创建一个简单的
        index_html_path = html_dir / "index.html"
        if not index_html_path.exists():
            default_index_html = """<!DOCTYPE html>
<html>
<head>
    <title>Nginx WebUI</title>
</head>
<body>
    <h1>Nginx is running!</h1>
    <p>This is the default page. Please configure your site.</p>
</body>
</html>
"""
            with open(index_html_path, "w", encoding="utf-8") as f:
                f.write(default_index_html)


def _create_default_config() -> None:
    """
    创建默认的 Nginx 配置文件（已弃用，改为使用 _create_default_config_for_version）
    保留此函数以保持向后兼容，但实际会尝试使用版本目录
    """
    try:
        config_path = get_config_path()
        # 如果配置文件不存在，会在 get_config_path 中自动创建
        if not config_path.exists():
            # 尝试获取活动版本
            active = get_active_version()
            if active is not None:
                _create_default_config_for_version(active["install_path"])
    except FileNotFoundError:
        # 如果没有版本，抛出更友好的错误
        raise FileNotFoundError(
            "未找到可用的 Nginx 版本。请先下载并编译一个 Nginx 版本。"
        )


def get_conf_d_dir() -> Path:
    """
    获取当前 Nginx 版本的 conf.d 配置目录路径

    Returns:
        conf.d 目录路径

    Raises:
        FileNotFoundError: 如果没有活动版本的 Nginx
    """
    active = get_active_version()
    if active is not None:
        conf_d_dir = active["install_path"] / "conf" / "conf.d"
        conf_d_dir.mkdir(parents=True, exist_ok=True)
        return conf_d_dir

    # 尝试从配置文件路径推断
    config_path = get_config_path()
    # config_path 应该是 versions/<version>/conf/nginx.conf
    # conf.d 应该在 versions/<version>/conf/conf.d
    if "conf" in str(config_path):
        conf_d_dir = config_path.parent / "conf.d"
        conf_d_dir.mkdir(parents=True, exist_ok=True)
        return conf_d_dir

    raise FileNotFoundError(
        "未找到可用的 Nginx 版本配置目录。请先下载并编译一个 Nginx 版本。"
    )


def get_config_content(use_working_copy: bool = True) -> str:
    """读取 Nginx 配置文件内容，如果不存在则创建默认配置"""
    if use_working_copy:
        config_path = ensure_working_config()
    else:
        config_path = get_config_path()
        if not config_path.exists():
            # 自动创建默认配置
            try:
                active = get_active_version()
                if active is not None:
                    _create_default_config_for_version(active["install_path"])
                else:
                    _create_default_config()
            except FileNotFoundError:
                raise FileNotFoundError(
                    "未找到可用的 Nginx 版本配置。请先下载并编译一个 Nginx 版本。"
                )

    with open(config_path, "r", encoding="utf-8") as f:
        return f.read()


def save_config_content(content: str) -> bool:
    """保存 Nginx 配置文件（写入工作副本）"""
    write_working_config_file("nginx.conf", content)
    return True


def test_config(use_working_copy: bool = True) -> Dict[str, Any]:
    """
    测试 Nginx 配置有效性，如果配置文件不存在则自动创建默认配置

    Returns:
        {
            "success": bool,
            "message": str,
            "output": str,
            "errors": List[str],
            "warnings": List[str]
        }
    """
    if use_working_copy:
        return _run_nginx_config_test(ensure_working_config_dir())

    config_path = get_config_path()
    if not config_path.exists():
        _create_default_config()
    return _run_nginx_config_test(config_path.parent)


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
    try:
        nginx_executable = get_nginx_executable_or_raise()
    except FileNotFoundError as e:
        return {
            "success": False,
            "message": str(e),
            "output": "",
        }

    try:
        config_path = get_config_path()
        active = get_active_version()

        # 构建重载命令
        cmd = [str(nginx_executable), "-s", "reload", "-c", str(config_path)]

        # 如果存在活动版本，需要指定 prefix 参数
        if active is not None:
            cmd.extend(["-p", str(active["install_path"])])

        result = subprocess.run(
            cmd,
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


def _simple_format_config(content: str) -> str:
    """
    简单的配置格式化（回退方案）

    Args:
        content: 配置内容

    Returns:
        格式化后的配置内容
    """
    lines = content.split("\n")
    formatted_lines = []
    indent_level = 0
    indent_size = 4  # 使用 4 个空格作为缩进

    for line in lines:
        stripped = line.strip()

        # 跳过空行
        if not stripped:
            formatted_lines.append("")
            continue

        # 处理注释
        if stripped.startswith("#"):
            formatted_lines.append(" " * (indent_level * indent_size) + stripped)
            continue

        # 处理闭合块（减少缩进）
        if stripped == "}":
            indent_level = max(0, indent_level - 1)
            formatted_lines.append(" " * (indent_level * indent_size) + stripped)
            continue

        # 处理打开块（增加缩进）
        if stripped.endswith("{"):
            formatted_lines.append(" " * (indent_level * indent_size) + stripped)
            indent_level += 1
            continue

        # 普通行
        formatted_lines.append(" " * (indent_level * indent_size) + stripped)

    return "\n".join(formatted_lines)


def format_config(content: str) -> Dict[str, Any]:
    """
    使用 crossplane 格式化 Nginx 配置文件

    Args:
        content: 配置内容

    Returns:
        {
            "success": bool,
            "formatted": str,
            "message": str
        }
    """
    import tempfile
    import os
    import shutil
    import sys

    temp_file = None
    formatted_file = None

    try:
        # 创建临时输入文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_file = f.name

        # 创建临时输出文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False, encoding="utf-8"
        ) as f:
            formatted_file = f.name

        # 首先尝试使用 crossplane 命令行工具
        crossplane_cmd = shutil.which("crossplane")
        if not crossplane_cmd:
            # 尝试使用 python -m crossplane
            python_cmd = shutil.which("python3") or shutil.which("python")
            if python_cmd:
                crossplane_cmd = python_cmd
                cmd = [
                    crossplane_cmd,
                    "-m",
                    "crossplane",
                    "format",
                    "-i",
                    "4",
                    "-o",
                    formatted_file,
                    temp_file,
                ]
            else:
                raise Exception("未找到 crossplane 命令或 Python 解释器")
        else:
            cmd = [crossplane_cmd, "format", "-i", "4", "-o", formatted_file, temp_file]

        # 执行格式化命令
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            # 读取格式化后的内容
            if os.path.exists(formatted_file):
                with open(formatted_file, "r", encoding="utf-8") as f:
                    formatted_content = f.read()
            else:
                # 如果输出文件不存在，可能是 crossplane 将结果输出到 stdout
                formatted_content = result.stdout if result.stdout else content
                # 如果 stdout 也为空，说明格式化可能有问题
                if not formatted_content or not formatted_content.strip():
                    formatted_content = content

            # 确保格式化后的内容不为空
            if not formatted_content or not formatted_content.strip():
                # 如果格式化后为空，使用简单格式化作为回退
                try:
                    formatted_content = _simple_format_config(content)
                    return {
                        "success": True,
                        "formatted": formatted_content,
                        "message": "配置格式化成功（使用简单格式化，crossplane 返回空内容）",
                    }
                except Exception:
                    return {
                        "success": False,
                        "formatted": content,
                        "message": "格式化后内容为空，已保留原配置。可能原因：1) crossplane 未正确安装 2) 配置文件语法错误 3) crossplane 不支持某些配置语法",
                    }

            return {
                "success": True,
                "formatted": formatted_content,
                "message": "配置格式化成功（使用 crossplane）",
            }
        else:
            error_msg = result.stderr or result.stdout or "格式化失败"
            # 如果 crossplane 失败，尝试使用简单格式化
            try:
                formatted_content = _simple_format_config(content)
                return {
                    "success": True,
                    "formatted": formatted_content,
                    "message": f"使用简单格式化（crossplane 失败: {error_msg[:100]}）",
                }
            except Exception:
                return {
                    "success": False,
                    "formatted": content,
                    "message": f"crossplane 格式化失败: {error_msg[:200]}",
                }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "formatted": content,
            "message": "格式化超时",
        }
    except ImportError:
        return {
            "success": False,
            "formatted": content,
            "message": "crossplane 未安装，请运行: pip install crossplane",
        }
    except Exception as e:
        # 如果 crossplane 格式化失败，使用简单的格式化逻辑作为回退
        try:
            formatted_content = _simple_format_config(content)
            return {
                "success": True,
                "formatted": formatted_content,
                "message": f"使用简单格式化（crossplane 不可用: {str(e)}）",
            }
        except Exception as fallback_error:
            return {
                "success": False,
                "formatted": content,
                "message": f"格式化出错: {str(e)}，回退方案也失败: {str(fallback_error)}",
            }
    finally:
        # 清理临时文件
        for file_path in [temp_file, formatted_file]:
            if file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except Exception:
                    pass


def _resolve_include_paths(content: str, conf_dir: Path) -> str:
    """
    将配置内容中的相对路径 include 指令转换为绝对路径

    Args:
        content: 配置内容
        conf_dir: 配置目录（通常是 versions/<version>/conf）

    Returns:
        转换后的配置内容
    """
    import re
    import os

    lines = content.split("\n")
    resolved_lines = []

    # include 指令的正则表达式
    # 匹配: include path; 或 include path/*.conf;
    include_pattern = re.compile(r"^(\s*)include\s+([^;]+);\s*(.*)$")

    for line in lines:
        match = include_pattern.match(line)
        if match:
            indent = match.group(1)
            include_path = match.group(2).strip().strip('"').strip("'")
            comment = match.group(3)

            # 如果是绝对路径，不需要转换
            if os.path.isabs(include_path):
                resolved_lines.append(line)
                continue

            # 将相对路径转换为绝对路径
            # 如果路径以 conf.d/ 开头，直接拼接
            if include_path.startswith("conf.d/"):
                abs_path = conf_dir / include_path
            elif include_path.startswith("../"):
                # 处理 ../ 的相对路径
                abs_path = conf_dir.parent / include_path[3:]
            elif include_path.startswith("./"):
                # 处理 ./ 的相对路径
                abs_path = conf_dir / include_path[2:]
            else:
                # 其他情况，假设相对于 conf 目录
                abs_path = conf_dir / include_path

            # 转换为绝对路径字符串，并保持引号风格
            abs_path_str = str(abs_path)
            # 如果原路径有引号，保持引号风格
            if '"' in match.group(2) or "'" in match.group(2):
                abs_path_str = f'"{abs_path_str}"'

            resolved_line = f"{indent}include {abs_path_str};"
            if comment:
                resolved_line += f" {comment}"
            resolved_lines.append(resolved_line)
        else:
            resolved_lines.append(line)

    return "\n".join(resolved_lines)


def validate_config(content: str) -> Dict[str, Any]:
    """
    校验 Nginx 配置内容（不保存到文件）

    Args:
        content: 配置内容

    Returns:
        {
            "success": bool,
            "message": str,
            "output": str,
            "errors": List[str],
            "warnings": List[str]
        }
    """
    import tempfile
    import os

    try:
        nginx_executable = get_nginx_executable_or_raise()
    except FileNotFoundError as e:
        return {
            "success": False,
            "message": str(e),
            "output": "",
            "errors": [],
            "warnings": [],
        }

    # 获取配置目录路径（用于解析相对路径）
    active = get_active_version()
    conf_dir = None
    install_path = None

    if active is not None:
        install_path = active["install_path"]
        conf_dir = install_path / "conf"
    else:
        # 如果没有活动版本，从当前配置文件路径推断
        try:
            config_path = get_config_path()
            # 如果配置文件在 versions/<version>/conf/ 目录下
            if "versions" in str(config_path) and "conf" in str(config_path):
                conf_dir = config_path.parent  # conf 目录
                if conf_dir.name == "conf":
                    install_path = conf_dir.parent  # versions/<version> 目录
            else:
                # 尝试从配置文件路径推断
                config = get_config()
                versions_root = Path(config.nginx.versions_root)
                if not versions_root.is_absolute():
                    backend_dir = Path(__file__).resolve().parents[2]
                    versions_root = (backend_dir / versions_root).resolve()

                if versions_root.exists():
                    # 查找所有版本目录，使用第一个找到的
                    for version_dir in sorted(versions_root.iterdir(), reverse=True):
                        if version_dir.is_dir():
                            conf_file = version_dir / "conf" / "nginx.conf"
                            if conf_file.exists():
                                install_path = version_dir
                                conf_dir = version_dir / "conf"
                                break
        except Exception:
            pass

    # 如果无法确定配置目录，使用默认处理
    if conf_dir is None or not conf_dir.exists():
        return {
            "success": False,
            "message": "无法确定 Nginx 配置目录，请确保已安装 Nginx 版本",
            "output": "",
            "errors": ["无法确定 Nginx 配置目录"],
            "warnings": [],
        }

    # 将配置内容中的相对路径转换为绝对路径
    resolved_content = _resolve_include_paths(content, conf_dir)

    # 创建临时文件保存配置内容
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False, encoding="utf-8"
        ) as f:
            f.write(resolved_content)
            temp_file = f.name

        # 构建测试命令
        cmd = [str(nginx_executable), "-t", "-c", temp_file]

        # 必须指定 prefix 参数，这样 nginx 才能正确找到 mime.types 等文件
        if install_path is not None:
            # 使用安装路径作为 prefix
            cmd.extend(["-p", str(install_path)])

        # 使用 nginx -t -c 测试临时配置文件
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        # 解析错误和警告，提取详细信息
        errors = []
        warnings = []
        import re

        # Nginx 错误格式通常为：
        # nginx: [emerg] unexpected end of file, expecting ";" or "}" in /path/to/file.conf:10
        # nginx: [warn] conflicting server name "example.com" on 0.0.0.0:80, ignored in /path/to/file.conf:5
        # nginx: configuration file /path/to/file.conf test failed
        
        error_pattern = re.compile(
            r'nginx:\s*\[(emerg|alert|crit|error)\]\s*(.+?)(?:\s+in\s+(.+?):(\d+))?',
            re.IGNORECASE
        )
        warn_pattern = re.compile(
            r'nginx:\s*\[warn\]\s*(.+?)(?:\s+in\s+(.+?):(\d+))?',
            re.IGNORECASE
        )
        test_failed_pattern = re.compile(
            r'nginx:\s*configuration\s+file\s+(.+?)\s+test\s+failed',
            re.IGNORECASE
        )

        lines = output.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 检查是否是错误行
            error_match = error_pattern.search(line)
            if error_match:
                error_level = error_match.group(1).upper()
                error_msg = error_match.group(2).strip()
                file_path = error_match.group(3) if error_match.group(3) else None
                line_num = error_match.group(4) if error_match.group(4) else None
                
                # 构建详细的错误信息
                error_detail = f"[{error_level}] {error_msg}"
                if file_path and line_num:
                    error_detail += f"\n  位置: {file_path} 第 {line_num} 行"
                elif file_path:
                    error_detail += f"\n  文件: {file_path}"
                
                errors.append(error_detail)
                continue
            
            # 检查是否是警告行
            warn_match = warn_pattern.search(line)
            if warn_match:
                warn_msg = warn_match.group(1).strip()
                file_path = warn_match.group(2) if warn_match.group(2) else None
                line_num = warn_match.group(3) if warn_match.group(3) else None
                
                # 构建详细的警告信息
                warn_detail = f"警告: {warn_msg}"
                if file_path and line_num:
                    warn_detail += f"\n  位置: {file_path} 第 {line_num} 行"
                elif file_path:
                    warn_detail += f"\n  文件: {file_path}"
                
                warnings.append(warn_detail)
                continue
            
            # 检查是否是测试失败总结
            failed_match = test_failed_pattern.search(line)
            if failed_match:
                file_path = failed_match.group(1)
                errors.append(f"配置文件测试失败: {file_path}")
                continue
            
            # 如果没有匹配到特定格式，但包含错误关键词，也加入错误列表
            if "error" in line.lower() or "failed" in line.lower():
                if line not in errors:  # 避免重复
                    errors.append(line)
            elif "warn" in line.lower() or "warning" in line.lower():
                if line not in warnings:  # 避免重复
                    warnings.append(line)

        # 构建详细的消息
        if success:
            message = "配置校验成功"
            if warnings:
                message += f"，但有 {len(warnings)} 个警告"
        else:
            if errors:
                error_count = len(errors)
                message = f"配置校验失败，发现 {error_count} 个错误"
                if error_count == 1:
                    # 如果是单个错误，在消息中包含简要信息
                    first_error = errors[0].split("\n")[0]
                    message += f": {first_error[:100]}"
            else:
                message = "配置校验失败"

        return {
            "success": success,
            "message": message,
            "output": output,
            "errors": errors,
            "warnings": warnings,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "配置校验超时",
            "output": "",
            "errors": ["配置校验超时"],
            "warnings": [],
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"配置校验出错: {str(e)}",
            "output": "",
            "errors": [str(e)],
            "warnings": [],
        }
    finally:
        # 清理临时文件
        if temp_file and os.path.exists(temp_file):
            try:
                os.unlink(temp_file)
            except Exception:
                pass


def validate_working_config_file(content: str, path: str = "nginx.conf") -> Dict[str, Any]:
    """校验替换某个工作副本文件后的完整配置目录。"""
    try:
        relative = _relative_config_path(path)
        source_dir = ensure_working_config_dir()
        with tempfile.TemporaryDirectory(prefix="nginx-webui-conf-") as tmp:
            temp_dir = Path(tmp) / "conf"
            _copy_config_dir(source_dir, temp_dir)
            target = temp_dir / relative
            target.resolve().relative_to(temp_dir.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return _run_nginx_config_test(temp_dir)
    except Exception as e:
        return {
            "success": False,
            "message": f"配置校验出错: {str(e)}",
            "output": "",
            "errors": [str(e)],
            "warnings": [],
        }


def _find_named_block(lines: List[str], name: str, start_index: int = 0) -> Optional[Tuple[int, int]]:
    pattern = re.compile(rf"^\s*{re.escape(name)}\s*\{{")
    for index in range(start_index, len(lines)):
        if not pattern.search(lines[index]):
            continue
        depth = lines[index].count("{") - lines[index].count("}")
        end = index
        while end + 1 < len(lines) and depth > 0:
            end += 1
            depth += lines[end].count("{") - lines[end].count("}")
        if depth == 0:
            return index, end
    return None


def _find_http_child_blocks(http_lines: List[str]) -> List[Dict[str, Any]]:
    block_names = ("server", "upstream", "map", "geo", "split_clients")
    block_pattern = re.compile(r"^\s*(server|upstream|map|geo|split_clients)\b.*\{")
    blocks = []
    index = 0
    while index < len(http_lines):
        line = http_lines[index]
        match = block_pattern.search(line)
        if not match:
            index += 1
            continue

        # Only split blocks directly under http{}, not nested location blocks.
        before_depth = 0
        for prior in http_lines[:index]:
            before_depth += prior.count("{") - prior.count("}")
        if before_depth != 0 or match.group(1) not in block_names:
            index += 1
            continue

        depth = line.count("{") - line.count("}")
        end = index
        while end + 1 < len(http_lines) and depth > 0:
            end += 1
            depth += http_lines[end].count("{") - http_lines[end].count("}")
        if depth == 0:
            blocks.append(
                {
                    "kind": match.group(1),
                    "start": index,
                    "end": end,
                    "content": "\n".join(http_lines[index : end + 1]).strip() + "\n",
                }
            )
            index = end + 1
        else:
            index += 1
    return blocks


def _extract_server_names(block_content: str) -> List[str]:
    names = []
    for line in block_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        match = re.search(r"\bserver_name\s+([^;]+);", stripped)
        if not match:
            continue
        for name in match.group(1).split():
            cleaned = name.strip().strip(";")
            if cleaned:
                names.append(cleaned)
    return names


def _safe_conf_name(value: str) -> str:
    value = value.strip().lower()
    if not value or value == "_":
        value = "default"
    value = value.replace("*.", "wildcard-")
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = value.strip(".-") or "default"
    if not value.endswith(".conf"):
        value += ".conf"
    return value


def _unique_file_path(directory: Path, filename: str) -> Path:
    base = filename[:-5] if filename.endswith(".conf") else filename
    candidate = directory / filename
    index = 2
    while candidate.exists():
        candidate = directory / f"{base}-{index}.conf"
        index += 1
    return candidate


def split_legacy_config() -> Dict[str, Any]:
    """将工作副本中的单文件 nginx.conf 拆成推荐的 nginx.conf + conf.d/*.conf。"""
    working_dir = ensure_working_config_dir()
    main_path = working_dir / "nginx.conf"
    content = main_path.read_text(encoding="utf-8")
    legacy_path = working_dir / "nginx.conf.legacy"
    legacy_path.write_text(content, encoding="utf-8")

    lines = content.splitlines()
    http_block = _find_named_block(lines, "http")
    if not http_block:
        return {
            "success": False,
            "message": "未找到 http 块，无法自动拆分",
            "created_files": [],
            "test_result": None,
        }

    http_start, http_end = http_block
    http_body = lines[http_start + 1 : http_end]
    child_blocks = _find_http_child_blocks(http_body)
    if not child_blocks:
        return {
            "success": False,
            "message": "未发现可拆分的 server/upstream/map 等 http 级配置块",
            "created_files": [],
            "test_result": None,
        }

    conf_d_dir = working_dir / "conf.d"
    conf_d_dir.mkdir(parents=True, exist_ok=True)
    created_files = []
    remove_lines = set()
    shared_blocks = []
    server_blocks = []

    for block in child_blocks:
        remove_lines.update(range(block["start"], block["end"] + 1))
        if block["kind"] == "server":
            server_blocks.append(block)
        else:
            shared_blocks.append(block)

    if shared_blocks:
        shared_path = _unique_file_path(conf_d_dir, "00-shared.conf")
        shared_path.write_text(
            "\n".join(block["content"].rstrip() for block in shared_blocks) + "\n",
            encoding="utf-8",
        )
        created_files.append(str(shared_path.relative_to(working_dir)).replace("\\", "/"))

    for block in server_blocks:
        names = [name for name in _extract_server_names(block["content"]) if name != "_"]
        filename = _safe_conf_name(names[0] if names else "default")
        server_path = _unique_file_path(conf_d_dir, filename)
        server_path.write_text(block["content"], encoding="utf-8")
        created_files.append(str(server_path.relative_to(working_dir)).replace("\\", "/"))

    new_http_body = [
        line for idx, line in enumerate(http_body) if idx not in remove_lines
    ]
    has_conf_d_include = any(
        re.search(r"^\s*include\s+conf\.d/\*\.conf\s*;", line)
        for line in new_http_body
    )
    if not has_conf_d_include:
        while new_http_body and not new_http_body[-1].strip():
            new_http_body.pop()
        new_http_body.extend(["", "    include conf.d/*.conf;"])

    new_lines = (
        lines[: http_start + 1]
        + new_http_body
        + lines[http_end:]
    )
    main_path.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    test_result = test_config(use_working_copy=True)
    return {
        "success": True,
        "message": f"已拆分 {len(server_blocks)} 个 server 配置和 {len(shared_blocks)} 个共享配置块",
        "created_files": created_files,
        "legacy_file": "nginx.conf.legacy",
        "test_result": test_result,
    }


def get_merged_config_preview() -> str:
    """生成一个按常见 include 顺序拼接的只读配置预览。"""
    working_dir = ensure_working_config_dir()
    main_path = working_dir / "nginx.conf"
    chunks = [
        "# ===== nginx.conf =====",
        main_path.read_text(encoding="utf-8", errors="ignore"),
    ]
    conf_d_dir = working_dir / "conf.d"
    if conf_d_dir.exists():
        for file_path in sorted(conf_d_dir.rglob("*.conf"), key=lambda p: str(p.relative_to(conf_d_dir))):
            rel = str(file_path.relative_to(working_dir)).replace("\\", "/")
            chunks.extend(
                [
                    "",
                    f"# ===== {rel} =====",
                    file_path.read_text(encoding="utf-8", errors="ignore"),
                ]
            )
    return "\n".join(chunks).rstrip() + "\n"


def get_nginx_status() -> Dict[str, Any]:
    """
    获取 Nginx 运行状态

    Returns:
        {
            "running": bool,
            "pid": Optional[int],
            "pid_file": Optional[str],  # PID文件路径
            "version": Optional[str],
            "uptime": Optional[str],
            "install_path": Optional[str]
        }
    """
    from datetime import datetime
    import re

    config = get_config()
    active = get_active_version()
    nginx_executable = _resolve_nginx_executable()

    # 即使没有可执行文件路径，也尝试检测nginx进程
    # 这样可以处理容器重启后PID文件过期的情况

    try:
        pid = None
        running = False
        uptime_str = None
        pid_file_path = None  # 实际使用的PID文件路径
        
        # 获取实际使用的PID文件路径（从配置或默认位置）
        def _get_actual_pid_file() -> Optional[Path]:
            """获取nginx实际使用的PID文件路径"""
            if active is None:
                return None
            
            install_path = active["install_path"]
            
            # 尝试从nginx.conf解析pid路径
            try:
                nginx_conf = install_path / "conf" / "nginx.conf"
                if nginx_conf.exists():
                    conf_content = nginx_conf.read_text(encoding="utf-8")
                    pid_match = re.search(r"^\s*pid\s+([^;]+);", conf_content, re.MULTILINE)
                    if pid_match:
                        pid_path_str = pid_match.group(1).strip().strip('"').strip("'")
                        pid_path = Path(pid_path_str)
                        if not pid_path.is_absolute():
                            pid_path = install_path / pid_path_str
                        return pid_path
            except Exception:
                pass
            
            # 返回默认位置
            return install_path / "logs" / "nginx.pid"
        
        actual_pid_file = _get_actual_pid_file()
        if actual_pid_file:
            pid_file_path = str(actual_pid_file)

        # 尝试从 pid 文件读取主进程 PID
        if active is not None:
            pid_file = actual_pid_file if actual_pid_file else active["install_path"] / "logs" / "nginx.pid"
        else:
            # 尝试从配置文件路径推断 pid 文件位置
            try:
                config_path = get_config_path()
                # config_path 通常是 versions/<version>/conf/nginx.conf
                # pid 文件应该在 versions/<version>/logs/nginx.pid
                install_path = config_path.parent.parent  # 从 conf 向上两级到版本目录
                pid_file = install_path / "logs" / "nginx.pid"
            except:
                pid_file = None

        # 如果找到 pid 文件，读取 PID
        if pid_file and pid_file.exists():
            try:
                with open(pid_file, "r") as f:
                    pid = int(f.read().strip())

                # 使用 psutil 检查进程是否在运行并获取运行时间
                if PSUTIL_AVAILABLE:
                    try:
                        process = psutil.Process(pid)
                        if process.is_running():
                            running = True
                            # 获取运行时间
                            create_time = datetime.fromtimestamp(process.create_time())
                            now = datetime.now()
                            uptime_delta = now - create_time

                            # 格式化运行时间
                            days = uptime_delta.days
                            hours, remainder = divmod(uptime_delta.seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)

                            if days > 0:
                                uptime_str = f"{days}天{hours}小时{minutes}分钟"
                            elif hours > 0:
                                uptime_str = f"{hours}小时{minutes}分钟"
                            elif minutes > 0:
                                uptime_str = f"{minutes}分钟{seconds}秒"
                            else:
                                uptime_str = f"{seconds}秒"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        running = False
                        pid = None
                else:
                    # 如果没有 psutil，使用 os.kill 简单检查进程是否存在
                    try:
                        import os

                        os.kill(pid, 0)  # 发送信号 0 检查进程是否存在
                        running = True
                        uptime_str = "无法获取（需要 psutil）"
                    except (OSError, ProcessLookupError):
                        running = False
                        pid = None
            except (ValueError, IOError):
                pass

        # 如果没有从 pid 文件获取到，尝试查找 nginx 主进程
        # 改进：即使没有nginx_executable，也尝试查找（通过进程名称）
        if not running and PSUTIL_AVAILABLE:
            try:
                # 查找nginx主进程（通过进程名称"nginx"或命令行包含nginx）
                versions_root = _get_versions_root() if active is None else None
                
                for proc in psutil.process_iter(
                    ["pid", "name", "cmdline", "create_time", "exe"]
                ):
                    try:
                        proc_name = proc.info.get("name", "").lower()
                        cmdline = proc.info.get("cmdline") or []
                        cmdline_str = " ".join(cmdline).lower()
                        
                        # 检查是否是nginx进程
                        is_nginx = (
                            proc_name == "nginx" 
                            or "nginx" in proc_name
                            or any("nginx" in str(c).lower() for c in cmdline)
                        )
                        
                        if not is_nginx:
                            continue
                            
                        # 检查是否是主进程（包含master process或配置文件参数）
                        is_master = (
                            "master process" in cmdline_str
                            or any(c.endswith(".conf") for c in cmdline)
                        )
                        
                        if not is_master:
                            continue
                        
                        # 找到nginx主进程
                        pid = proc.info["pid"]
                        running = True
                        
                        # 尝试从命令行获取可执行文件路径（用于后续操作）
                        if cmdline and len(cmdline) > 0:
                            potential_exe = Path(cmdline[0])
                            if potential_exe.exists() and nginx_executable is None:
                                nginx_executable = potential_exe
                        
                        # 尝试从进程信息获取可执行文件路径
                        try:
                            if proc.info.get("exe"):
                                potential_exe = Path(proc.info["exe"])
                                if potential_exe.exists() and nginx_executable is None:
                                    nginx_executable = potential_exe
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass

                        # 获取运行时间
                        create_time = datetime.fromtimestamp(
                            proc.info["create_time"]
                        )
                        now = datetime.now()
                        uptime_delta = now - create_time

                        days = uptime_delta.days
                        hours, remainder = divmod(uptime_delta.seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)

                        if days > 0:
                            uptime_str = f"{days}天{hours}小时{minutes}分钟"
                        elif hours > 0:
                            uptime_str = f"{hours}小时{minutes}分钟"
                        elif minutes > 0:
                            uptime_str = f"{minutes}分钟{seconds}秒"
                        else:
                            uptime_str = f"{seconds}秒"
                        break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue
            except Exception:
                pass
        elif not running and not PSUTIL_AVAILABLE:
            # 如果没有 psutil，尝试使用 pgrep 查找进程
            try:
                # 优先通过可执行文件路径查找
                if nginx_executable:
                    search_pattern = str(nginx_executable)
                else:
                    # 如果没有可执行文件路径，就搜索所有nginx进程
                    search_pattern = "nginx"
                
                result = subprocess.run(
                    ["pgrep", "-f", search_pattern],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    pids = result.stdout.strip().split("\n")
                    pid = int(pids[0]) if pids else None
                    running = pid is not None
                    if running:
                        uptime_str = "无法获取（需要 psutil）"
            except Exception:
                pass

        # 获取版本信息（来自 nginx 可执行文件本身）
        version = None
        version_detail = None
        try:
            version_result = subprocess.run(
                [str(nginx_executable), "-v"], capture_output=True, text=True, timeout=5
            )
            if version_result.stderr:
                version_detail = version_result.stderr.strip()
                # 提取版本号（例如：nginx version: nginx/1.28.0）
                import re

                match = re.search(r"nginx/([\d.]+)", version_detail)
                if match:
                    version = match.group(1)
        except Exception:
            pass

        info: Dict[str, Any] = {
            "running": running,
            "pid": pid,
            "pid_file": pid_file_path,  # 添加PID文件路径
            "version": version,
            "version_detail": version_detail,
            "uptime": uptime_str,
            "available": True,
        }
        # 如果是通过多版本管理启动的 Nginx，补充当前活动版本号及目录名称
        if active is not None:
            info["active_version"] = active["version"]
            info["directory"] = active[
                "directory"
            ]  # 使用目录简称（如：1.28.0 或 last）
            info["binary"] = str(active["executable"])
            # 如果没有版本信息，使用活动版本号
            if not version:
                info["version"] = active["version"]

        return info
    except Exception as e:
        return {
            "running": False,
            "pid": False,
            "pid_file": None,
            "version": None,
            "uptime": None,
            "error": str(e),
            "available": True,
        }


# ==================== SSL 配置相关函数 ====================

import re as _re


def _find_server_blocks(content: str) -> List[Dict[str, Any]]:
    """
    解析 nginx 配置文件中的所有 server block

    Args:
        content: nginx 配置文件内容

    Returns:
        List[Dict]: server block 列表，每个元素包含 start, end, content, server_names
    """
    blocks = []
    lines = content.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 查找 server 块的开始
        if _re.match(r'^server\s*\{', line) or _re.match(r'^server\{', line):
            start_line = i
            brace_count = line.count('{') - line.count('}')
            block_lines = [lines[i]]

            i += 1
            while i < len(lines) and brace_count > 0:
                block_lines.append(lines[i])
                brace_count += lines[i].count('{') - lines[i].count('}')
                i += 1

            block_content = '\n'.join(block_lines)

            # 提取 server_name
            server_names = []
            for bl in block_lines:
                bl_stripped = bl.strip()
                if bl_stripped.startswith('#'):
                    continue
                name_match = _re.search(r'server_name\s+([^;]+);', bl_stripped)
                if name_match:
                    names_str = name_match.group(1).strip()
                    for name in names_str.split():
                        name = name.strip().rstrip(';')
                        if name:
                            server_names.append(name)

            # 检查是否已有 SSL 配置
            has_ssl = any(
                _re.search(r'listen\s+\d+\s+ssl', bl, _re.IGNORECASE)
                for bl in block_lines
            )
            has_443 = any(
                _re.search(r'listen\s+443', bl, _re.IGNORECASE)
                for bl in block_lines
            )

            blocks.append({
                'start': start_line,
                'end': i - 1,
                'content': block_content,
                'server_names': server_names,
                'has_ssl': has_ssl or has_443,
            })
        else:
            i += 1

    return blocks


def _domain_matches(domain: str, pattern: str) -> bool:
    """
    检查域名是否匹配模式（支持通配符）

    Args:
        domain: 要匹配的域名
        pattern: 模式（如 *.example.com）

    Returns:
        bool: 是否匹配
    """
    domain = domain.lower().strip()
    pattern = pattern.lower().strip()

    if pattern == domain:
        return True

    # 处理通配符模式 *.example.com
    if pattern.startswith('*.'):
        suffix = pattern[2:]  # example.com
        # domain 必须以 .suffix 结尾，或者等于 suffix
        if domain == suffix:
            return True
        if domain.endswith('.' + suffix):
            # 确保通配符前面有至少一个子域名部分
            prefix = domain[:-len(suffix) - 1]
            if prefix and '.' not in prefix:
                return True

    return False


def find_server_block_by_domain(config_content: str, domain: str) -> Optional[Dict[str, Any]]:
    """
    查找匹配指定域名的 server block

    Args:
        config_content: nginx 配置文件内容
        domain: 域名

    Returns:
        Optional[Dict]: 匹配的 server block 信息，包含 start, end, content, server_names
    """
    blocks = _find_server_blocks(config_content)

    # 先精确匹配
    for block in blocks:
        if domain in block['server_names']:
            return block

    # 再通配符匹配
    for block in blocks:
        for name in block['server_names']:
            if _domain_matches(domain, name):
                return block

    # 查找默认 server block (server_name _)
    for block in blocks:
        if '_' in block['server_names']:
            return block

    return None


def _add_ssl_to_server_block_content(block_content: str, cert_path: str, key_path: str) -> str:
    """
    在现有 server block 内容中添加 SSL 配置

    Args:
        block_content: server block 的内容
        cert_path: 证书文件路径
        key_path: 私钥文件路径

    Returns:
        str: 修改后的 server block 内容
    """
    lines = block_content.split('\n')
    new_lines = []

    has_listen_443_ssl = False
    has_listen_80 = False
    has_ssl_cert = False
    has_redirect = False
    insert_after_listen = -1
    first_listen_line = -1

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 检查是否已有 443 SSL listen
        if _re.search(r'listen\s+443\s+ssl', stripped, _re.IGNORECASE):
            has_listen_443_ssl = True

        # 检查是否有 listen 80
        if _re.search(r'listen\s+80', stripped, _re.IGNORECASE):
            has_listen_80 = True
            if first_listen_line < 0:
                first_listen_line = i

        # 检查是否已有 SSL 证书配置
        if 'ssl_certificate' in stripped and 'ssl_certificate_key' not in stripped:
            has_ssl_cert = True

        # 检查是否已有重定向
        if 'return 301' in stripped or 'return 302' in stripped or 'rewrite' in stripped:
            if 'https' in stripped:
                has_redirect = True

        new_lines.append(line)

    # 如果已经有完整的 SSL 配置，不重复添加
    if has_listen_443_ssl and has_ssl_cert:
        return block_content

    result_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # 在 listen 80 后面插入 443 SSL listen
        if _re.search(r'listen\s+80', stripped, _re.IGNORECASE) and not has_listen_443_ssl:
            indent = line[:len(line) - len(line.lstrip())]
            result_lines.append(line)
            # 插入 443 SSL listen
            result_lines.append(f'{indent}listen 443 ssl;')
            result_lines.append(f'{indent}listen [::]:443 ssl;')
            insert_after_listen = len(result_lines) - 1
            continue

        result_lines.append(line)

        # 在 server_name 行之后插入 SSL 证书配置
        if stripped.startswith('server_name') and not has_ssl_cert and insert_after_listen > 0:
            indent = line[:len(line) - len(line.lstrip())]
            # 获取正确的缩进（server_name 的缩进 + 一级）
            if indent:
                ssl_indent = indent + '    '
            else:
                ssl_indent = '    '
            result_lines.append('')
            result_lines.append(f'{indent}# SSL 证书配置')
            result_lines.append(f'{indent}ssl_certificate {cert_path};')
            result_lines.append(f'{indent}ssl_certificate_key {key_path};')
            result_lines.append('')
            result_lines.append(f'{indent}# SSL 协议和加密套件')
            result_lines.append(f'{indent}ssl_protocols TLSv1.2 TLSv1.3;')
            result_lines.append(f'{indent}ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;')
            result_lines.append(f'{indent}ssl_prefer_server_ciphers on;')
            has_ssl_cert = True  # 标记已添加

    # 如果没有 listen 80 也没有 listen 443，说明是空的 server block
    # 添加基本配置
    if not has_listen_80 and not has_listen_443_ssl:
        # 在 server { 后面插入
        final_lines = []
        inserted = False
        indent = '    '
        for i, line in enumerate(result_lines):
            final_lines.append(line)
            if not inserted and '{' in line and 'server' in line:
                final_lines.append(f'{indent}listen 80;')
                final_lines.append(f'{indent}listen 443 ssl;')
                final_lines.append(f'{indent}listen [::]:443 ssl;')
                inserted = True
        result_lines = final_lines

    return '\n'.join(result_lines)


def _create_ssl_server_blocks(domain: str, cert_path: str, key_path: str) -> str:
    """
    创建新的 SSL server block（包含 HTTP 80 重定向和 HTTPS 443 两个 block）

    Args:
        domain: 域名
        cert_path: 证书文件路径
        key_path: 私钥文件路径

    Returns:
        str: nginx server block 配置
    """
    return f"""
# HTTP -> HTTPS 重定向
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};
    return 301 https://$host$request_uri;
}}

# HTTPS server
server {{
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {domain};

    # SSL 证书配置
    ssl_certificate {cert_path};
    ssl_certificate_key {key_path};

    # SSL 协议和加密套件
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers on;

    # 日志配置
    access_log /app/data/logs/{domain}_access.log;
    error_log  /app/data/logs/{domain}_error.log;

    location / {{
        root   html;
        index  index.html index.htm;
    }}
}}
"""


def _find_server_block_file_by_domain(domain: str) -> Optional[Dict[str, Any]]:
    working_dir = ensure_working_config_dir()
    candidates = []
    conf_d_dir = working_dir / "conf.d"
    if conf_d_dir.exists():
        candidates.extend(sorted(conf_d_dir.rglob("*.conf")))
    main_config = working_dir / "nginx.conf"
    if main_config.exists():
        candidates.append(main_config)

    for candidate in candidates:
        try:
            content = candidate.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        block = find_server_block_by_domain(content, domain)
        if block:
            return {
                "path": candidate,
                "content": content,
                "block": block,
            }
    return None


def apply_ssl_config(domain: str, cert_path: str, key_path: str) -> Dict[str, Any]:
    """
    主函数：自动为域名添加 SSL 配置到 nginx 配置文件

    优先查找现有 server block，找到则添加 SSL 配置；找不到则创建新的 server block。
    修改保存到工作副本。

    Args:
        domain: 域名
        cert_path: 证书文件路径
        key_path: 私钥文件路径

    Returns:
        {
            "success": bool,
            "message": str,
            "action": str,  # "modified" 或 "created"
        }
    """
    try:
        match = _find_server_block_file_by_domain(domain)

        if match:
            # 修改现有 server block
            config_content = match["content"]
            existing_block = match["block"]
            lines = config_content.split('\n')

            # 替换现有的 server block 内容
            new_block_content = _add_ssl_to_server_block_content(
                existing_block['content'], cert_path, key_path
            )

            # 重建配置
            new_lines = lines[:existing_block['start']]
            new_lines.append(new_block_content)
            new_lines.extend(lines[existing_block['end'] + 1:])

            new_content = '\n'.join(new_lines)
            rel_path = str(match["path"].relative_to(ensure_working_config_dir())).replace("\\", "/")
            write_working_config_file(rel_path, new_content)

            return {
                "success": True,
                "message": f"已在现有 server block 中添加 SSL 配置（域名: {domain}）",
                "action": "modified"
            }
        else:
            # 创建新的 server block 到 conf.d
            new_blocks = _create_ssl_server_blocks(domain, cert_path, key_path)
            conf_d_dir = ensure_working_config_dir() / "conf.d"
            conf_d_dir.mkdir(parents=True, exist_ok=True)
            target = _unique_file_path(conf_d_dir, _safe_conf_name(domain))
            target.write_text(new_blocks.strip() + "\n", encoding="utf-8")

            return {
                "success": True,
                "message": f"已创建新的 SSL server block（域名: {domain}）",
                "action": "created"
            }
    except Exception as e:
        return {
            "success": False,
            "message": f"添加 SSL 配置失败: {str(e)}",
            "action": "error"
        }
