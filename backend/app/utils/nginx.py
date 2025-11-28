"""
Nginx 操作工具
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, Optional

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
        for version_dir in sorted(versions_root.iterdir(), key=lambda x: x.name, reverse=True):
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


def get_config_content() -> str:
    """读取 Nginx 配置文件内容，如果不存在则创建默认配置"""
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
    """保存 Nginx 配置文件"""
    config_path = get_config_path()

    # 确保目录存在
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(content)

    return True


def test_config() -> Dict[str, Any]:
    """
    测试 Nginx 配置有效性，如果配置文件不存在则自动创建默认配置

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
        
        # 如果配置文件不存在，自动创建默认配置
        if not config_path.exists():
            _create_default_config()
        
        active = get_active_version()
        
        # 构建测试命令
        cmd = [str(nginx_executable), "-t", "-c", str(config_path)]
        
        # 如果存在活动版本，需要指定 prefix 参数
        if active is not None:
            cmd.extend(["-p", str(active["install_path"])])
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
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
                cmd = [crossplane_cmd, "-m", "crossplane", "format", "-i", "4", "-o", formatted_file, temp_file]
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

    # 创建临时文件保存配置内容
    temp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".conf", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            temp_file = f.name

        # 构建测试命令
        active = get_active_version()
        cmd = [str(nginx_executable), "-t", "-c", temp_file]
        
        # 必须指定 prefix 参数，这样 nginx 才能正确找到 mime.types 等文件
        if active is not None:
            # 使用活动版本的安装路径作为 prefix
            cmd.extend(["-p", str(active["install_path"])])
        else:
            # 如果没有活动版本，需要从当前配置文件路径推断 prefix
            config_path = get_config_path()
            
            # 如果配置文件在 versions/<version>/conf/ 目录下
            # prefix 应该是 versions/<version> 目录
            if "versions" in str(config_path) and "conf" in str(config_path):
                # 从 conf/nginx.conf 向上找到 versions/<version> 目录
                current = config_path.parent  # conf 目录
                if current.name == "conf":
                    install_path = current.parent  # versions/<version> 目录
                    if install_path.exists() and install_path.is_dir():
                        cmd.extend(["-p", str(install_path)])
            else:
                # 尝试从配置文件路径推断
                # 如果配置文件在 nginx/versions/ 下，使用该版本目录作为 prefix
                config = get_config()
                versions_root = Path(config.nginx.versions_root)
                if not versions_root.is_absolute():
                    backend_dir = Path(__file__).resolve().parents[2]
                    versions_root = (backend_dir / versions_root).resolve()
                
                if versions_root.exists():
                    # 查找所有版本目录，尝试找到匹配的
                    for version_dir in sorted(versions_root.iterdir(), reverse=True):
                        if version_dir.is_dir():
                            conf_file = version_dir / "conf" / "nginx.conf"
                            if conf_file.exists():
                                cmd.extend(["-p", str(version_dir)])
                                break

        # 使用 nginx -t -c 测试临时配置文件
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        # 解析错误和警告
        errors = []
        warnings = []

        for line in output.split("\n"):
            line = line.strip()
            if not line:
                continue
            if "error" in line.lower() or "failed" in line.lower():
                errors.append(line)
            elif "warn" in line.lower() or "warning" in line.lower():
                warnings.append(line)

        return {
            "success": success,
            "message": "配置校验成功" if success else "配置校验失败",
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

    if nginx_executable is None or not nginx_executable.exists():
        info: Dict[str, Any] = {
            "running": False, 
            "pid": None, 
            "version": None,
            "available": False,
            "message": "Nginx 未安装或不可用"
        }
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

        info: Dict[str, Any] = {
            "running": running, 
            "pid": pid, 
            "version": version,
            "available": True
        }
        # 如果是通过多版本管理启动的 Nginx，可以补充当前活动版本号及安装路径
        if active is not None:
            info["active_version"] = active["version"]
            info["install_path"] = str(active["install_path"])
            info["binary"] = str(active["executable"])

        return info
    except Exception as e:
        return {"running": False, "pid": None, "version": None, "error": str(e)}
