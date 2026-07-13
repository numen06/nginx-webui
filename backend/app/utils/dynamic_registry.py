"""动态服务注册与 Nginx 配置生成工具。"""

import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse
import hashlib

from sqlalchemy.orm import Session

from app.config import get_config
from app.models import DynamicService, DynamicServiceInstance
from app.utils.nginx import (
    ensure_working_config_dir,
    get_config_dir,
    reload_nginx,
    test_config,
)
from app.utils.nginx_status_cache import clear_nginx_status_cache


DYNAMIC_UPSTREAM_FILE = "00-webui-dynamic-upstreams.conf"
DYNAMIC_LOCATION_INCLUDE = "include conf.d/webui-dynamic/locations/*.conf;"
RESERVED_ROUTE_PREFIXES = (
    "/api",
    "/assets",
    "/login",
    "/dashboard",
    "/config",
    "/logs",
    "/files",
    "/static-package",
    "/certificates",
    "/audit",
    "/nginx",
    "/git-sync",
    "/profile",
)


@dataclass
class DynamicServiceGroup:
    service_name: str
    route_prefix: str
    description: Optional[str]
    instances: List[DynamicServiceInstance]


def normalize_service_name(value: str) -> str:
    name = (value or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$", name):
        raise ValueError("服务名只能包含字母、数字、点、下划线和中划线，且需以字母或数字开头")
    return name


def normalize_instance_id(value: str) -> str:
    instance_id = (value or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,149}$", instance_id):
        raise ValueError("实例 ID 只能包含字母、数字、点、下划线、中划线和冒号")
    return instance_id


def instance_id_from_target_url(target_url: str) -> str:
    digest = hashlib.sha1(target_url.encode("utf-8")).hexdigest()[:12]
    return f"target-{digest}"


def normalize_route_prefix(value: str) -> str:
    prefix = (value or "").strip()
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    prefix = re.sub(r"/+", "/", prefix).rstrip("/")
    if not prefix or prefix == "/":
        raise ValueError("路径前缀不能为根路径 /")
    if not re.match(r"^/[A-Za-z0-9._~!$&'()*+,;=:@/-]+$", prefix):
        raise ValueError("路径前缀包含非法字符")
    for reserved in RESERVED_ROUTE_PREFIXES:
        if prefix == reserved or prefix.startswith(reserved + "/"):
            raise ValueError(f"路径前缀 {prefix} 与系统保留路径 {reserved} 冲突")
    return prefix


def normalize_target_url(value: str) -> str:
    raw = (value or "").strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("目标地址必须是 http:// 或 https:// 开头的地址")
    if parsed.path not in ("", "/") or parsed.params or parsed.query or parsed.fragment:
        raise ValueError("目标地址只支持协议、主机和端口，不支持路径或查询参数")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    return f"{parsed.scheme}://{host}:{port}"


def safe_nginx_name(value: str) -> str:
    name = value.strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = name.strip("_") or "service"
    return name[:80]


def normalize_domain_suffix(value: Optional[str]) -> str:
    suffix = (value or "").strip().strip(".").lower()
    if not suffix:
        return ""
    label = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    if not re.match(rf"^{label}(?:\.{label})*$", suffix):
        raise ValueError("动态服务域名后缀格式无效")
    return suffix


def dynamic_service_hosts(service_name: str) -> List[str]:
    base_host = service_name.strip().lower().strip(".")
    hosts = [base_host]
    suffix = normalize_domain_suffix(get_config().dynamic_registry.domain_suffix)
    if suffix:
        hosts.append(f"{base_host}.{suffix}")
    return hosts


def validate_route_prefix_available(
    db: Session,
    route_prefix: str,
    service_id: Optional[int] = None,
) -> None:
    query = db.query(DynamicService).filter(DynamicService.route_prefix == route_prefix)
    if service_id is not None:
        query = query.filter(DynamicService.id != service_id)
    if query.first():
        raise ValueError(f"路径前缀已被其他服务使用: {route_prefix}")


def active_service_groups(db: Session) -> List[DynamicServiceGroup]:
    now = datetime.now()
    services = (
        db.query(DynamicService)
        .filter(DynamicService.enabled == True)
        .order_by(DynamicService.service_name.asc())
        .all()
    )
    groups: List[DynamicServiceGroup] = []
    for service in services:
        instances = []
        for instance in service.instances:
            if instance.status != "active":
                continue
            expires_at = instance.last_heartbeat_at + timedelta(seconds=instance.ttl_seconds)
            if expires_at <= now:
                continue
            instances.append(instance)
        if instances:
            groups.append(
                DynamicServiceGroup(
                    service_name=service.service_name,
                    route_prefix=service.route_prefix,
                    description=service.description,
                    instances=instances,
                )
            )
    return groups


def _target_server(target_url: str) -> str:
    parsed = urlparse(target_url)
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return f"{host}:{port}"


def _target_scheme(target_url: str) -> str:
    return urlparse(target_url).scheme


def _upstream_name(service_name: str) -> str:
    return f"webui_dynamic_{safe_nginx_name(service_name)}"


def _proxy_directives(
    scheme: str,
    upstream: str,
    proxy_pass_suffix: str,
    route_prefix: Optional[str] = None,
    indent: str = "    ",
) -> str:
    forwarded_prefix = (
        f"{indent}proxy_set_header X-Forwarded-Prefix {route_prefix};\n"
        if route_prefix
        else ""
    )
    return f"""{indent}proxy_pass {scheme}://{upstream}{proxy_pass_suffix};
{indent}proxy_http_version 1.1;
{indent}proxy_set_header Host $host;
{indent}proxy_set_header X-Real-IP $remote_addr;
{indent}proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
{indent}proxy_set_header X-Forwarded-Proto $scheme;
{indent}proxy_set_header X-Forwarded-Host $host;
{forwarded_prefix}{indent}proxy_set_header Upgrade $http_upgrade;
{indent}proxy_set_header Connection $connection_upgrade;
{indent}proxy_read_timeout 3600s;
{indent}proxy_send_timeout 3600s;"""


def render_dynamic_nginx_config(groups: List[DynamicServiceGroup]) -> Dict[str, str]:
    upstream_chunks = [
        "# Generated by Nginx WebUI dynamic registry. Do not edit manually.",
        "map $http_upgrade $connection_upgrade {",
        "    default upgrade;",
        "    '' close;",
        "}",
    ]
    location_files: Dict[str, str] = {}

    for group in groups:
        schemes = {_target_scheme(instance.target_url) for instance in group.instances}
        if len(schemes) != 1:
            raise ValueError(f"服务 {group.service_name} 的实例不能混用 http 和 https")

        upstream = _upstream_name(group.service_name)
        upstream_chunks.append("")
        upstream_chunks.append(f"upstream {upstream} {{")
        for instance in sorted(group.instances, key=lambda item: item.instance_id):
            upstream_chunks.append(f"    server {_target_server(instance.target_url)};")
        upstream_chunks.append("}")

        route_prefix = group.route_prefix
        scheme = next(iter(schemes))
        path_proxy_directives = _proxy_directives(
            scheme=scheme,
            upstream=upstream,
            proxy_pass_suffix="/",
            route_prefix=route_prefix,
        )
        location_content = f"""# Generated by Nginx WebUI dynamic registry for {group.service_name}.
location = {route_prefix} {{
{path_proxy_directives}
}}

location {route_prefix}/ {{
{path_proxy_directives}
}}
"""
        location_files[f"{safe_nginx_name(group.service_name)}.conf"] = location_content

        host_names = dynamic_service_hosts(group.service_name)
        host_proxy_directives = _proxy_directives(
            scheme=scheme,
            upstream=upstream,
            proxy_pass_suffix="",
            indent="        ",
        )
        upstream_chunks.append("")
        upstream_chunks.append(f"# Host access for dynamic service {group.service_name}: {', '.join(host_names)}")
        upstream_chunks.append("server {")
        upstream_chunks.append("    listen 80;")
        upstream_chunks.append(f"    server_name {' '.join(host_names)};")
        upstream_chunks.append("")
        upstream_chunks.append("    location / {")
        upstream_chunks.append(host_proxy_directives)
        upstream_chunks.append("    }")
        upstream_chunks.append("}")

    return {
        "upstreams": "\n".join(upstream_chunks).rstrip() + "\n",
        **{f"locations/{name}": content for name, content in location_files.items()},
    }


def get_dynamic_config_preview(db: Session) -> str:
    rendered = render_dynamic_nginx_config(active_service_groups(db))
    chunks = [f"# ===== {DYNAMIC_UPSTREAM_FILE} =====", rendered["upstreams"].rstrip()]
    for path in sorted(key for key in rendered.keys() if key.startswith("locations/")):
        chunks.extend(["", f"# ===== webui-dynamic/{path} =====", rendered[path].rstrip()])
    return "\n".join(chunks).rstrip() + "\n"


def _find_server_block(content: str, preferred: bool = False) -> Optional[tuple[int, int]]:
    lines = content.splitlines()
    candidates = []
    index = 0
    while index < len(lines):
        if not re.match(r"^\s*server\s*\{", lines[index]):
            index += 1
            continue
        start = index
        depth = lines[index].count("{") - lines[index].count("}")
        while index + 1 < len(lines) and depth > 0:
            index += 1
            depth += lines[index].count("{") - lines[index].count("}")
        if depth == 0:
            block = "\n".join(lines[start : index + 1])
            score = 0
            if "location /api/" in block:
                score = 3
            elif "server_name _" in block:
                score = 2
            elif preferred:
                score = 1
            candidates.append((score, start, index))
        index += 1
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _, start, end = candidates[0]
    return start, end


def _ensure_dynamic_include(conf_dir: Path) -> Optional[Path]:
    conf_d_dir = conf_dir / "conf.d"
    conf_d_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(conf_d_dir.glob("*.conf"))

    for file_path in files:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        if DYNAMIC_LOCATION_INCLUDE in content:
            return file_path

    selected: Optional[Path] = None
    selected_block: Optional[tuple[int, int]] = None
    for file_path in files:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        block = _find_server_block(content)
        if block:
            selected = file_path
            selected_block = block
            if "location /api/" in content:
                break

    if selected is None or selected_block is None:
        return None

    lines = selected.read_text(encoding="utf-8", errors="ignore").splitlines()
    _, end = selected_block
    indent = "    "
    include_line = f"{indent}{DYNAMIC_LOCATION_INCLUDE}"
    lines.insert(end, "")
    lines.insert(end + 1, include_line)
    selected.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return selected


def _write_dynamic_files(conf_dir: Path, rendered: Dict[str, str]) -> None:
    conf_d_dir = conf_dir / "conf.d"
    locations_dir = conf_d_dir / "webui-dynamic" / "locations"
    locations_dir.mkdir(parents=True, exist_ok=True)

    upstream_path = conf_d_dir / DYNAMIC_UPSTREAM_FILE
    upstream_path.write_text(rendered["upstreams"], encoding="utf-8")

    for old_file in locations_dir.glob("*.conf"):
        old_file.unlink()
    for key, content in rendered.items():
        if not key.startswith("locations/"):
            continue
        target = locations_dir / Path(key).name
        target.write_text(content, encoding="utf-8")

    include_file = _ensure_dynamic_include(conf_dir)
    has_locations = any(key.startswith("locations/") for key in rendered)
    if has_locations and include_file is None:
        raise RuntimeError("未找到可插入动态 location include 的 server 配置")


def _snapshot_config_dir(conf_dir: Path) -> Path:
    snapshot_root = Path(tempfile.mkdtemp(prefix="nginx-webui-dynamic-"))
    snapshot = snapshot_root / "conf"
    shutil.copytree(conf_dir, snapshot)
    return snapshot


def _restore_config_dir(snapshot: Path, conf_dir: Path) -> None:
    if conf_dir.exists():
        shutil.rmtree(conf_dir)
    shutil.copytree(snapshot, conf_dir)


def _cleanup_snapshot(snapshot: Path) -> None:
    try:
        shutil.rmtree(snapshot.parent)
    except Exception:
        pass


def apply_dynamic_registry(db: Session) -> Dict[str, object]:
    """将当前动态服务表渲染到实际 Nginx 配置并 reload。"""
    conf_dir = get_config_dir()
    snapshot = _snapshot_config_dir(conf_dir)
    rendered = render_dynamic_nginx_config(active_service_groups(db))

    try:
        _write_dynamic_files(conf_dir, rendered)
        test_result = test_config(use_working_copy=False)
        if not test_result.get("success"):
            _restore_config_dir(snapshot, conf_dir)
            return {
                "success": False,
                "message": "动态服务配置测试失败，已回滚",
                "test_result": test_result,
            }

        reload_result = reload_nginx()
        if not reload_result.get("success"):
            _restore_config_dir(snapshot, conf_dir)
            reload_nginx()
            return {
                "success": False,
                "message": "Nginx 重载失败，已回滚动态服务配置",
                "reload_result": reload_result,
            }

        try:
            working_dir = ensure_working_config_dir()
            _write_dynamic_files(working_dir, rendered)
        except Exception:
            pass

        clear_nginx_status_cache()
        return {
            "success": True,
            "message": "动态服务配置已生效",
            "test_result": test_result,
            "reload_result": reload_result,
        }
    except Exception as exc:
        _restore_config_dir(snapshot, conf_dir)
        return {
            "success": False,
            "message": f"动态服务配置生效失败，已回滚: {exc}",
        }
    finally:
        _cleanup_snapshot(snapshot)
