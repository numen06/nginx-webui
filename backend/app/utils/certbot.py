"""
Certbot 工具封装
"""
import os
import subprocess
import re
import shutil
import threading
import time
import uuid
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from urllib.parse import quote
from urllib.request import urlopen, Request

from app.config import get_config

# DNS 手动验证：挂起的 certbot 进程（必须与后续按回车为同一进程，否则 ACME challenge 失效）
_dns_jobs: Dict[str, Dict[str, Any]] = {}
_dns_jobs_lock = threading.Lock()
_JOB_TTL_SEC = 1800  # 30 分钟
_certbot_exec_lock = threading.Lock()


def _get_certbot_lock_holder_pid(config_dir: Path) -> Optional[int]:
    """读取 certbot 锁文件中的 PID。"""
    lock_file = config_dir / ".lock"
    if not lock_file.exists():
        return None
    try:
        content = lock_file.read_text(encoding="utf-8").strip()
        return int(content)
    except (ValueError, OSError):
        return None


def _cleanup_certbot_lock(config_dir: Path, max_age_seconds: int = 300) -> None:
    """清理超时且已无存活进程占用的 certbot 锁文件。"""
    lock_file = config_dir / ".lock"
    if not lock_file.exists():
        return
    try:
        stat = lock_file.stat()
    except OSError:
        return
    if time.time() - stat.st_mtime <= max_age_seconds:
        return

    pid = _get_certbot_lock_holder_pid(config_dir)
    if pid is None:
        try:
            lock_file.unlink()
        except OSError:
            pass
        return

    try:
        os.kill(pid, 0)
        # 进程仍存活，保留锁文件。
        return
    except ProcessLookupError:
        pass
    except PermissionError:
        return
    except OSError:
        pass

    try:
        lock_file.unlink()
    except OSError:
        pass


def _run_certbot(
    cmd: List[str],
    *,
    timeout: int = 300,
    lock_timeout: int = 10,
    cleanup_lock: bool = True,
) -> Dict[str, Any]:
    """统一执行 certbot 命令：全局互斥 + 残留锁清理 + 超时兜底。"""
    config_dir: Optional[Path] = None
    for i, arg in enumerate(cmd):
        if arg == "--config-dir" and i + 1 < len(cmd):
            config_dir = Path(cmd[i + 1])
            break

    if cleanup_lock and config_dir:
        _cleanup_certbot_lock(config_dir)

    acquired = _certbot_exec_lock.acquire(timeout=lock_timeout)
    if not acquired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "",
            "output": "",
            "error_code": "certbot_busy",
            "message": "Certbot 正在被其他任务占用，请稍后重试",
            "timed_out": False,
        }

    try:
        if cleanup_lock and config_dir:
            _cleanup_certbot_lock(config_dir)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout or "",
                "stderr": stderr or "",
                "output": (stdout or "") + (stderr or ""),
                "error_code": None,
                "message": "",
                "timed_out": False,
            }
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
            return {
                "success": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "output": "",
                "error_code": "timeout",
                "message": f"certbot 命令超时（{timeout}秒）",
                "timed_out": True,
            }
    finally:
        _certbot_exec_lock.release()


def _cleanup_stale_dns_jobs() -> None:
    now = time.time()
    with _dns_jobs_lock:
        stale = [
            jid
            for jid, j in _dns_jobs.items()
            if now - j.get("created_at", 0) > _JOB_TTL_SEC
        ]
        for jid in stale:
            j = _dns_jobs.pop(jid, None)
            if j and j.get("proc"):
                try:
                    j["proc"].terminate()
                    j["proc"].wait(timeout=5)
                except Exception:
                    try:
                        j["proc"].kill()
                    except Exception:
                        pass
            if j and j.get("holds_exec_lock"):
                try:
                    _certbot_exec_lock.release()
                except RuntimeError:
                    pass


def classify_certbot_failure(
    output: str, validation_method: str = "http"
) -> Tuple[str, str, List[str]]:
    """
    根据 certbot 输出分类错误，返回 (error_code, 友好说明, 修复建议列表)
    """
    o = (output or "").lower()
    full = output or ""

    suggestions: List[str] = []

    if "too many certificates already issued" in o or "rate limit" in o:
        return (
            "rate_limit",
            "Let's Encrypt 签发频率受限（同一注册域名每周有数量限制）",
            [
                "等待约 1 周后重试，或使用其他 ACME 测试环境（staging）",
                "检查是否在短时间内重复申请了同一域名",
                "确认是否与其他服务共享了同一注册域名的配额",
            ],
        )

    if "another instance of certbot is already running" in o:
        return (
            "certbot_busy",
            "Certbot 正在被其他任务占用，请稍后重试",
            [
                "如果你刚发起过 DNS 验证，请先在当前流程完成“检测 DNS -> 完成申请”",
                "等待 10-30 秒后重试，避免同时发起多个申请/续期任务",
                "若长期不恢复，请检查是否有残留 certbot 进程或锁文件",
            ],
        )

    if "certbot: command not found" in o or (
        "no such file or directory" in o and "certbot" in full.lower()
    ):
        return (
            "certbot_missing",
            "未找到 certbot 可执行文件",
            ["在服务器上安装 certbot，并在配置中设置正确的 certbot_path"],
        )

    if "permission denied" in o or "operation not permitted" in o:
        return (
            "permission",
            "权限不足，certbot 无法写入证书目录或读取配置",
            [
                "使用具有权限的用户运行本服务，或为 certbot 配置可写目录",
                "Linux 上 /etc/letsencrypt 通常需要 root 或加入相应组",
            ],
        )

    if "connection refused" in o or "timed out" in o or "timeout" in o:
        if validation_method == "http":
            return (
                "http_unreachable",
                "HTTP 验证时无法从公网访问验证地址（连接被拒绝或超时）",
                [
                    "确认域名 A/AAAA 已解析到本服务器公网 IP",
                    "确认防火墙放行 80 端口，且 Nginx 正在监听 80",
                    "确认 static_dir（webroot）与 Nginx 中 ACME 文件根目录一致",
                ],
            )
        return (
            "network",
            "网络连接失败或超时",
            ["检查服务器出网、DNS 解析及防火墙设置"],
        )

    if "dns problem" in o or "dns query problem" in o or "no valid a records" in o:
        return (
            "dns_resolution",
            "域名 DNS 解析异常",
            ["确认域名已正确解析到本机（HTTP 验证）或 DNS 面板中 TXT 已生效"],
        )

    if "incorrect txt record" in o or "expected a dns txt record" in o:
        return (
            "dns_txt_mismatch",
            "DNS TXT 记录与要求不一致或未生效",
            [
                "在 DNS 控制台添加 _acme-challenge 的 TXT 记录",
                "等待 DNS 传播后再继续（可用「检测 DNS」功能）",
                "确认记录名、值与界面显示完全一致（无多余空格）",
            ],
        )

    if "invalid response" in o or "http-01" in o or "detail: invalid response" in o:
        return (
            "http_validation_failed",
            "HTTP-01 验证失败：Let's Encrypt 无法从公网获取验证文件",
            [
                "确认域名已解析到本服务器",
                "确认 Nginx 对 `/.well-known/acme-challenge/` 可访问且指向 webroot",
                "关闭仅 HTTPS 跳转对验证路径的影响，或临时允许 80 访问",
            ],
        )

    if "urn:ietf:params:acme:error:unauthorized" in o:
        return (
            "acme_unauthorized",
            "ACME 授权验证失败",
            [
                "按验证方式检查 HTTP 可访问性或 DNS TXT 是否正确",
                "若使用 DNS 验证，请确认 TXT 已全球生效后再继续",
            ],
        )

    if "could not bind" in o or "address already in use" in o:
        return (
            "port_in_use",
            "端口被占用或 certbot 无法绑定所需端口",
            ["检查 80/443 是否被其他程序占用；HTTP 验证建议使用 webroot 模式"],
        )

    # 默认：附带截断输出便于排查
    snippet = full.strip().replace("\r", "")
    if len(snippet) > 800:
        snippet = snippet[:800] + "\n...(输出已截断)"
    return (
        "unknown",
        "证书申请失败，请查看下方 certbot 输出排查",
        [
            "确认 certbot、openssl 已安装且配置路径正确",
            "根据输出中的具体英文错误在搜索引擎或 Let's Encrypt 社区查找",
            f"原始信息摘要：{snippet[:200]}..." if len(snippet) > 200 else snippet,
        ],
    )


def _enrich_failure_result(
    result: Dict[str, Any], validation_method: str
) -> Dict[str, Any]:
    if result.get("success"):
        result.setdefault("error_code", None)
        result.setdefault("suggestions", None)
        return result
    out = result.get("output") or ""
    code, msg, sug = classify_certbot_failure(out, validation_method)
    result["error_code"] = code
    result["message"] = msg if result.get("message") in ("证书申请失败", "证书续期失败") else result.get("message", msg)
    result["suggestions"] = sug
    return result


def _domain_ssl_basename(domain: str) -> str:
    """用于 ssl_dir 下文件名/子目录名，避免 Windows 等环境下非法字符。"""
    d = (domain or "").strip()
    if not d:
        return "_empty"
    return (
        d.replace("*", "_star_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def get_certbot_config_dir() -> Path:
    """获取 certbot config-dir（默认 /app/data/letsencrypt）。"""
    config = get_config()
    p = Path(config.nginx.certbot_config_dir or "/app/data/letsencrypt")
    if not p.is_absolute():
        try:
            p = p.resolve()
        except OSError:
            pass
    return p


def get_certbot_live_root() -> Path:
    return get_certbot_config_dir() / "live"


def get_certbot_renewal_root() -> Path:
    return get_certbot_config_dir() / "renewal"


def validate_certbot_lineage_segment(name: str) -> str:
    """
    校验 Certbot lineage / live 子目录名（与 renewal 配置文件主文件名一致），防止路径穿越。
    与 routers.certificates._validate_letsencrypt_live_domain_segment 规则一致。
    """
    if not name or not isinstance(name, str):
        raise ValueError("证书目录名不能为空")
    d = name.strip()
    if not d:
        raise ValueError("证书目录名不能为空")
    if ".." in d or "/" in d or "\\" in d or "\x00" in d:
        raise ValueError("非法证书目录名：不可包含路径分隔符或 ..")
    return d


def _parse_renewal_conf_paths(conf_text: str) -> Dict[str, str]:
    """从 certbot renewal .conf 顶层键值行解析路径（忽略注释与 [section]）。"""
    paths: Dict[str, str] = {}
    for line in (conf_text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
            continue
        if " = " not in line:
            continue
        key, val = line.split(" = ", 1)
        key, val = key.strip(), val.strip()
        if key in ("archive_dir", "cert", "privkey", "chain", "fullchain"):
            paths[key] = val
    return paths


def renewal_conf_referenced_paths_ready(paths: Dict[str, str]) -> bool:
    """
    若 renewal 配置中列出的 archive 与主要 PEM 路径在本机均存在，则 certbot 通常可识别并续签该 lineage。
    """
    archive_dir = paths.get("archive_dir")
    if not archive_dir:
        return False
    ad = Path(archive_dir)
    if not ad.is_dir():
        return False
    for key in ("cert", "privkey", "chain", "fullchain"):
        fp = paths.get(key)
        if not fp:
            return False
        if not Path(fp).is_file():
            return False
    return True


def _rewrite_renewal_conf_paths(conf_text: str, local_config_dir: Path) -> str:
    """将 renewal 配置中的关键路径重写到当前主机的 certbot config-dir。"""
    local_root = str(local_config_dir).replace("\\", "/").rstrip("/")

    def map_value(key: str, value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return raw
        normalized = raw.replace("\\", "/")
        p = Path(normalized)
        lineage = p.parent.name if p.name else p.name
        if key == "archive_dir":
            lineage = p.name
            return f"{local_root}/archive/{lineage}"
        if key in ("cert", "privkey", "chain", "fullchain"):
            return f"{local_root}/live/{lineage}/{p.name}"
        return raw

    out_lines: List[str] = []
    for line in (conf_text or "").splitlines():
        if " = " not in line:
            out_lines.append(line)
            continue
        key, val = line.split(" = ", 1)
        key_s = key.strip()
        if key_s in ("archive_dir", "cert", "privkey", "chain", "fullchain"):
            out_lines.append(f"{key} = {map_value(key_s, val)}")
        else:
            out_lines.append(line)
    return "\n".join(out_lines) + ("\n" if conf_text.endswith("\n") else "")


def install_renewal_config(conf_bytes: bytes, lineage_name: str) -> Dict[str, Any]:
    """
    将导出的 Certbot renewal 配置写入 <certbot_config_dir>/renewal/<lineage>.conf。

    Returns:
        success, message, renewal_available（配置指向的 archive 等路径是否已存在于本机）,
        installed_path, error_code（失败时）
    """
    try:
        lineage = validate_certbot_lineage_segment(lineage_name)
    except ValueError as e:
        return {
            "success": False,
            "message": str(e),
            "renewal_available": False,
            "installed_path": None,
            "error_code": "invalid_lineage_name",
        }

    try:
        renewal_root = get_certbot_renewal_root()
        renewal_root_res = renewal_root.resolve()
    except OSError as e:
        return {
            "success": False,
            "message": f"无法解析 renewal 目录: {e}",
            "renewal_available": False,
            "installed_path": None,
            "error_code": "renewal_dir_unresolvable",
        }

    target = (renewal_root / f"{lineage}.conf").resolve()
    try:
        if target.parent.resolve() != renewal_root_res:
            return {
                "success": False,
                "message": "renewal 目标路径异常，已拒绝写入",
                "renewal_available": False,
                "installed_path": None,
                "error_code": "path_safety",
            }
    except OSError as e:
        return {
            "success": False,
            "message": f"无法校验 renewal 路径: {e}",
            "renewal_available": False,
            "installed_path": None,
            "error_code": "path_safety",
        }

    try:
        text = conf_bytes.decode("utf-8")
    except Exception:
        text = conf_bytes.decode("utf-8", errors="replace")
    text = _rewrite_renewal_conf_paths(text, get_certbot_config_dir())
    conf_bytes = text.encode("utf-8")

    path_map = _parse_renewal_conf_paths(text)
    materialized = renewal_conf_referenced_paths_ready(path_map)

    try:
        renewal_root.mkdir(parents=True, exist_ok=True)
        target.write_bytes(conf_bytes)
        try:
            os.chmod(target, 0o644)
        except OSError:
            pass
    except OSError as e:
        return {
            "success": False,
            "message": f"写入 renewal 配置失败: {e}",
            "renewal_available": False,
            "installed_path": None,
            "error_code": "write_failed",
            "suggestions": [
                f"确保运行用户对 {renewal_root} 可写（常见为 root）",
                "Docker 场景请挂载 app/data 并确保 certbot_config_dir 指向持久化目录",
            ],
        }

    if materialized:
        msg = (
            "已安装 Certbot renewal 配置，且配置中的 archive 路径在本机存在，"
            "certbot renew 可识别该 lineage"
        )
    else:
        msg = (
            "已安装 renewal 配置，但配置中指向的 archive/live 文件在本机不完整或不存在；"
            "仅复制 fullchain/privkey 时 certbot renew 仍无法续签，需在同一主机保留完整 "
            "<certbot_config_dir>/archive/<lineage>/ 或在目标机重新申请"
        )

    return {
        "success": True,
        "message": msg,
        "renewal_available": materialized,
        "installed_path": str(target),
        "error_code": None,
        "suggestions": None,
    }


def ensure_pem_bundle_from_stored_paths(
    domain: str, cert_path: str, key_path: str
) -> bool:
    """
    从已有证书链、私钥补齐磁盘布局：
    - ssl_dir/{basename}.pem：与 .crt 同内容（证书链 PEM，与 .crt/.key 同级）
    - ssl_dir/{basename}/fullchain.pem、privkey.pem：Certbot 风格子目录

    Returns:
        True：上述 .pem 与子目录两文件均存在；False：源文件不存在或写入失败。
    """
    cert_p = Path(cert_path)
    key_p = Path(key_path)
    if not cert_p.is_file() or not key_p.is_file():
        return False

    config = get_config()
    ssl_dir = Path(config.nginx.ssl_dir)
    if not ssl_dir.is_absolute():
        try:
            ssl_dir = ssl_dir.resolve()
        except OSError:
            pass
    ssl_dir.mkdir(parents=True, exist_ok=True)

    base = _domain_ssl_basename(domain)
    target_flat_pem = ssl_dir / f"{base}.pem"

    try:
        if cert_p.resolve() != target_flat_pem.resolve():
            shutil.copy2(cert_p, target_flat_pem)
    except OSError:
        pass

    subdir = ssl_dir / base
    target_fc = subdir / "fullchain.pem"
    target_pk = subdir / "privkey.pem"

    try:
        subdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cert_p, target_fc)
        shutil.copy2(key_p, target_pk)
    except OSError:
        pass

    return (
        target_flat_pem.is_file()
        and target_fc.is_file()
        and target_pk.is_file()
    )


def copy_certificate_files(domain: str, lineage_name: Optional[str] = None) -> Dict[str, Any]:
    """
    从 certbot 的 live 目录复制到配置项 nginx.ssl_dir（默认 data/ssl），供 Nginx 直接使用。

    Args:
        domain: 业务域名（用于生成 ssl 子目录名）
        lineage_name: Certbot lineage 目录名（若提供则优先使用，否则回退到 domain）

    写入内容：
    - {basename}.crt：与 fullchain.pem 相同（完整证书链，作 ssl_certificate）
    - {basename}.key：与 privkey.pem 相同（私钥，作 ssl_certificate_key）
    - {basename}.pem：与 .crt 相同（证书链 PEM 扩展名，与上两项同级）
    - {basename}/fullchain.pem、{basename}/privkey.pem：与官方示例一致的命名，便于手写配置或挂载

    basename 由域名规范化得到（通配符 * 变为 _star_ 等）。
    """
    config = get_config()

    # 优先用 lineage_name，否则回退到 domain
    _live_name = lineage_name or domain
    certbot_live_dir = get_certbot_live_root() / _live_name
    source_cert = certbot_live_dir / "fullchain.pem"
    source_key = certbot_live_dir / "privkey.pem"

    if not source_cert.exists():
        return {
            "success": False,
            "message": f"Certbot 证书文件不存在: {source_cert}",
            "cert_path": None,
            "key_path": None,
            "certificate_pem": None,
            "fullchain_pem": None,
            "privkey_pem": None,
            "ssl_subdir": None,
        }

    if not source_key.exists():
        return {
            "success": False,
            "message": f"Certbot 私钥文件不存在: {source_key}",
            "cert_path": None,
            "key_path": None,
            "certificate_pem": None,
            "fullchain_pem": None,
            "privkey_pem": None,
            "ssl_subdir": None,
        }

    ssl_dir = Path(config.nginx.ssl_dir)
    ssl_dir.mkdir(parents=True, exist_ok=True)

    base = _domain_ssl_basename(domain)
    target_cert = ssl_dir / f"{base}.crt"
    target_key = ssl_dir / f"{base}.key"
    target_flat_pem = ssl_dir / f"{base}.pem"
    subdir = ssl_dir / base
    target_fullchain_pem = subdir / "fullchain.pem"
    target_privkey_pem = subdir / "privkey.pem"

    try:
        shutil.copy2(source_cert, target_cert)
        shutil.copy2(source_key, target_key)
        shutil.copy2(source_cert, target_flat_pem)
        subdir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_cert, target_fullchain_pem)
        shutil.copy2(source_key, target_privkey_pem)

        return {
            "success": True,
            "message": "证书已复制到本系统 ssl 目录（含 Nginx 常用 fullchain.pem / privkey.pem）",
            "cert_path": str(target_cert.resolve()),
            "key_path": str(target_key.resolve()),
            "certificate_pem": str(target_flat_pem.resolve()),
            "fullchain_pem": str(target_fullchain_pem.resolve()),
            "privkey_pem": str(target_privkey_pem.resolve()),
            "ssl_subdir": str(subdir.resolve()),
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"复制证书文件失败: {str(e)}",
            "cert_path": None,
            "key_path": None,
            "certificate_pem": None,
            "fullchain_pem": None,
            "privkey_pem": None,
            "ssl_subdir": None,
        }


def request_certificate(
    domains: List[str], email: str, validation_method: str = "http"
) -> Dict[str, Any]:
    """
    通过 certbot 申请证书（仅支持 HTTP(webroot)；DNS 请使用 start_dns_manual_challenge + complete_dns_manual_challenge）

    Returns:
        含 success, message, output, cert_path, key_path, error_code, suggestions
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)

    if not certbot_path.exists():
        return {
            "success": False,
            "message": f"Certbot 可执行文件不存在: {certbot_path}",
            "output": "",
            "cert_path": None,
            "key_path": None,
            "error_code": "certbot_missing",
            "suggestions": [
                "安装 certbot 并设置配置项 nginx.certbot_path",
                "Docker 镜像中需包含 certbot 或挂载宿主机可执行文件",
            ],
        }

    if validation_method == "dns":
        return {
            "success": False,
            "message": "DNS 验证请使用界面上的分步流程：获取 TXT → 配置 DNS → 检测 → 完成申请",
            "output": "",
            "cert_path": None,
            "key_path": None,
            "error_code": "use_dns_wizard",
            "suggestions": [
                "在「申请证书」中选择 DNS 验证后按步骤操作",
                "勿直接调用本接口进行 DNS 验证（需保持同一 certbot 会话）",
            ],
        }

    if validation_method != "http":
        return {
            "success": False,
            "message": f"不支持的验证方式: {validation_method}",
            "output": "",
            "cert_path": None,
            "key_path": None,
            "error_code": "unsupported_validation",
            "suggestions": ["请选择 http 或 dns"],
        }

    # 构建 certbot 命令（仅 HTTP）
    cmd = [
        str(certbot_path),
        "certonly",
        "--config-dir",
        str(get_certbot_config_dir()),
        "--non-interactive",
        "--agree-tos",
        "--email",
        email,
        "--expand",
    ]

    for domain in domains:
        cmd.extend(["-d", domain])

    cmd.append("--webroot")
    cmd.extend(["--webroot-path", str(Path(config.nginx.static_dir))])

    try:
        run = _run_certbot(cmd, timeout=300)
        if run.get("timed_out"):
            return {
                "success": False,
                "message": "证书申请超时",
                "output": "",
                "cert_path": None,
                "key_path": None,
                "error_code": "timeout",
                "suggestions": [
                    "检查网络与 Let's Encrypt 连通性",
                    "确认验证过程无长时间阻塞",
                ],
            }
        if run.get("error_code") == "certbot_busy":
            return {
                "success": False,
                "message": "Certbot 正在被其他任务占用，请稍后重试",
                "output": "",
                "cert_path": None,
                "key_path": None,
                "error_code": "certbot_busy",
                "suggestions": [
                    "避免同时执行申请、续签、DNS 验证",
                    "等待 10-30 秒后重试",
                ],
            }

        success = bool(run.get("success"))
        output = run.get("output", "")

        cert_path = None
        key_path = None

        if success and domains:
            domain = domains[0]
            cert_path = str(get_certbot_live_root() / domain / "fullchain.pem")
            key_path = str(get_certbot_live_root() / domain / "privkey.pem")

            if not Path(cert_path).exists():
                cert_path = None
            if not Path(key_path).exists():
                key_path = None

        ret: Dict[str, Any] = {
            "success": success,
            "message": "证书申请成功" if success else "证书申请失败",
            "output": output,
            "cert_path": cert_path,
            "key_path": key_path,
        }
        if not success:
            ret = _enrich_failure_result(ret, "http")
        else:
            ret["error_code"] = None
            ret["suggestions"] = None
        return ret
    except Exception as e:
        return {
            "success": False,
            "message": f"证书申请出错: {str(e)}",
            "output": "",
            "cert_path": None,
            "key_path": None,
            "error_code": "exception",
            "suggestions": ["查看服务端日志", str(e)],
        }


def parse_dns_challenge_from_output(text: str) -> Optional[Tuple[str, str]]:
    """
    从 certbot manual DNS 输出中解析 TXT 记录名与值。
    返回 (record_name, record_value)
    """
    if not text:
        return None
    # 常见格式：_acme-challenge.example.com with the following value:\n\nTOKEN
    m = re.search(
        r"(_acme-challenge[^\s]+)\s+with the following value:\s*\r?\n\s*\r?\n?\s*([^\s\r\n]+)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return (m.group(1).strip(), m.group(2).strip())
    # 备选：分行
    m2 = re.search(
        r"(_acme-challenge[^\s]+)",
        text,
        re.IGNORECASE,
    )
    if m2:
        lines = text.splitlines()
        name = m2.group(1).strip()
        for i, line in enumerate(lines):
            if name in line and "following value" in line.lower():
                # 向后找第一个像 token 的行
                for j in range(i + 1, min(i + 8, len(lines))):
                    cand = lines[j].strip()
                    if len(cand) > 20 and re.match(r"^[A-Za-z0-9_-]+$", cand):
                        return (name, cand)
    return None


def parse_all_dns_challenges_from_output(text: str) -> List[Tuple[str, str]]:
    """
    从 certbot manual DNS 输出中解析所有 TXT 记录名与值。
    通配符证书需要两个 TXT 记录，此函数返回全部。
    """
    if not text:
        return []
    results: List[Tuple[str, str]] = []
    # 匹配所有 "with the following value:" 后面的 token
    seen_values: set = set()
    for m in re.finditer(
        r"(_acme-challenge[^\s]+)\s+with the following value:\s*\r?\n\s*\r?\n?\s*([^\s\r\n]+)",
        text,
        re.IGNORECASE | re.DOTALL,
    ):
        name = m.group(1).strip()
        value = m.group(2).strip()
        if value not in seen_values:
            seen_values.add(value)
            results.append((name, value))
    if results:
        return results
    # 备选：分行查找
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "following value" in line.lower():
            name_match = re.search(r"(_acme-challenge[^\s]+)", line, re.IGNORECASE)
            if not name_match:
                continue
            name = name_match.group(1).strip()
            for j in range(i + 1, min(i + 8, len(lines))):
                cand = lines[j].strip()
                if len(cand) > 20 and re.match(r"^[A-Za-z0-9_-]+$", cand):
                    if cand not in seen_values:
                        seen_values.add(cand)
                        results.append((name, cand))
                    break
    return results


def start_dns_manual_challenge(domain: str, email: str) -> Dict[str, Any]:
    """
    启动 certbot manual DNS 验证进程，解析出 TXT 后保持进程等待 stdin 回车。
    """
    _cleanup_stale_dns_jobs()
    domain_norm = (domain or "").strip().lower()

    # 同一域名复用已有挂起会话：TXT 与 job_id 不变（避免刷新/重复点击拿到新 challenge）
    with _dns_jobs_lock:
        for jid, job in _dns_jobs.items():
            p = job.get("proc")
            if not p or p.poll() is not None:
                continue
            job_domain = (job.get("domain") or "").strip().lower()
            if (
                job_domain == domain_norm
                and job.get("record_name")
                and job.get("record_value")
            ):
                return {
                    "success": True,
                    "message": "已复用进行中的 DNS 验证，记录值不变，请继续配置 DNS 后完成申请",
                    "job_id": jid,
                    "record_name": job["record_name"],
                    "record_value": job["record_value"],
                    "output": job.get("stdout_tail", ""),
                    "reused": True,
                }

    # 其他域名已有会话在跑：不能并行再启 certbot
    with _dns_jobs_lock:
        for jid, job in _dns_jobs.items():
            p = job.get("proc")
            if p and p.poll() is None:
                return {
                    "success": False,
                    "message": "已有其他域名的证书申请正在进行，请先完成或取消该会话后再申请新域名",
                    "job_id": jid,
                    "record_name": job.get("record_name"),
                    "record_value": job.get("record_value"),
                    "output": job.get("stdout_tail", ""),
                    "error_code": "certbot_busy",
                    "suggestions": [
                        "先完成当前域名的 DNS 验证与「完成申请」",
                        "或等待当前会话结束（约 30 分钟内有效）后再试其他域名",
                    ],
                }

    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)

    if not certbot_path.exists():
        return {
            "success": False,
            "message": f"Certbot 可执行文件不存在: {certbot_path}",
            "job_id": None,
            "record_name": None,
            "record_value": None,
            "output": "",
        }

    cmd = [
        str(certbot_path),
        "certonly",
        "--config-dir",
        str(get_certbot_config_dir()),
        "--manual",
        "--preferred-challenges",
        "dns",
        "-d",
        domain,
        "--email",
        email,
        "--agree-tos",
        "--no-eff-email",
        "--expand",
    ]

    # 通配符域名自动附带根域名（如 *.example.com → 同时申请 example.com）
    _base_domain = None
    if domain.startswith("*."):
        _base_domain = domain[2:]
        if _base_domain and _base_domain not in cmd:
            cmd.extend(["-d", _base_domain])

    config_dir = get_certbot_config_dir()
    _cleanup_certbot_lock(config_dir)
    acquired = _certbot_exec_lock.acquire(timeout=10)
    if not acquired:
        return {
            "success": False,
            "message": "Certbot 正在被其他任务占用，请稍后重试",
            "job_id": None,
            "record_name": None,
            "record_value": None,
            "output": "",
            "error_code": "certbot_busy",
            "suggestions": ["等待当前 certbot 任务完成后重试"],
        }

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except Exception as e:
        try:
            _certbot_exec_lock.release()
        except RuntimeError:
            pass
        return {
            "success": False,
            "message": f"无法启动 certbot: {str(e)}",
            "job_id": None,
            "record_name": None,
            "record_value": None,
            "output": "",
        }

    buf: List[str] = []
    deadline = time.time() + 120
    all_challenges: List[Tuple[str, str]] = []
    # 记录上一次遇到 "Press Enter" 后已经解析的 challenge 数量，
    # 当连续几次读取都没有新 challenge 时说明 certbot 已输出全部要求
    last_challenge_count = 0
    stable_rounds = 0

    assert proc.stdout is not None
    while time.time() < deadline:
        if proc.poll() is not None:
            rest = proc.stdout.read() or ""
            full = "".join(buf) + rest
            try:
                _certbot_exec_lock.release()
            except RuntimeError:
                pass
            return {
                "success": False,
                "message": "certbot 在显示 DNS 要求前已退出，请查看输出",
                "job_id": None,
                "record_name": None,
                "record_value": None,
                "output": full,
                "error_code": "certbot_exited_early",
            }
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        buf.append(line)
        full = "".join(buf)
        all_challenges = parse_all_dns_challenges_from_output(full)

        if all_challenges:
            last_challenge_count = len(all_challenges)
            stable_rounds = 0
        elif last_challenge_count > 0:
            stable_rounds += 1
            # 已经有至少一个 challenge，且连续 15 次读取（约 0.75 秒）没有新 challenge，
            # 并且输出中包含 "Press Enter"，说明 certbot 已输出全部 DNS 要求
            if stable_rounds >= 15 and "press enter" in full.lower():
                break

    if not all_challenges:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        try:
            _certbot_exec_lock.release()
        except RuntimeError:
            pass
        full = "".join(buf)
        return {
            "success": False,
            "message": "未能从 certbot 输出中解析 DNS TXT 记录，请确认 certbot 版本与语言为英文输出",
            "job_id": None,
            "record_name": None,
            "record_value": None,
            "output": full,
            "error_code": "dns_parse_failed",
            "suggestions": [
                "服务器上 certbot 需为英文界面输出",
                "尝试手动安装 certbot 或升级版本",
            ],
        }

    job_id = str(uuid.uuid4())
    record_name, record_value = all_challenges[0]
    # 收集所有不同的 TXT 值（通配符场景有多个）
    all_record_values = [v for _, v in all_challenges]
    with _dns_jobs_lock:
        _dns_jobs[job_id] = {
            "proc": proc,
            "domain": domain,
            "email": email,
            "record_name": record_name,
            "record_value": record_value,
            "all_record_values": all_record_values,
            "challenge_count": len(all_challenges),
            "created_at": time.time(),
            "stdout_tail": "".join(buf),
            "holds_exec_lock": True,
            "_base_domain": _base_domain,
        }

    extra_msg = ""
    if len(all_challenges) > 1:
        extra_msg = f"（共 {len(all_challenges)} 个 TXT 记录需添加，请全部配置后再完成申请）"

    return {
        "success": True,
        "message": f"已获取 DNS 验证信息，请在 DNS 中添加 TXT 后点击检测并完成申请{extra_msg}",
        "job_id": job_id,
        "record_name": record_name,
        "record_value": record_value,
        "all_record_values": all_record_values,
        "challenge_count": len(all_challenges),
        "output": "".join(buf),
        "reused": False,
    }


def get_pending_dns_challenge_for_domain(domain: str) -> Dict[str, Any]:
    """
    查询指定域名是否有尚未完成的 manual DNS 会话（certbot 仍在等待回车）。
    用于页面刷新后恢复同一组 TXT / job_id。
    """
    _cleanup_stale_dns_jobs()
    domain_norm = (domain or "").strip().lower()
    if not domain_norm:
        return {
            "success": False,
            "message": "请提供域名",
            "job_id": None,
            "record_name": None,
            "record_value": None,
        }
    with _dns_jobs_lock:
        for jid, job in _dns_jobs.items():
            p = job.get("proc")
            if not p or p.poll() is not None:
                continue
            if (job.get("domain") or "").strip().lower() != domain_norm:
                continue
            rn = job.get("record_name")
            rv = job.get("record_value")
            if rn and rv:
                all_vals = job.get("all_record_values", [rv])
                return {
                    "success": True,
                    "job_id": jid,
                    "record_name": rn,
                    "record_value": rv,
                    "all_record_values": all_vals,
                    "challenge_count": job.get("challenge_count", 1),
                }
    return {
        "success": False,
        "message": "当前没有该域名未完成的 DNS 验证会话",
        "job_id": None,
        "record_name": None,
        "record_value": None,
    }


def _split_txt_rr_data(raw: Any) -> List[str]:
    """
    从 DoH JSON 的 TXT 的 data 字段拆出若干子串（支持一条 RR 内多段 "a" "b" 形式）。
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            out.extend(_split_txt_rr_data(item))
        return out
    s = str(raw).strip()
    if not s:
        return []
    parts = re.findall(r'"([^"]*)"', s)
    if parts:
        return parts
    if s.startswith('"') and s.endswith('"') and len(s) >= 2:
        return [s[1:-1]]
    return [s]


def _txt_expected_matches_found(expected: str, fragments: List[str]) -> bool:
    """判断 ACME 期望 token 是否出现在 DNS 返回的 TXT 片段中（大小写敏感，兼容分段/空白）。"""
    exp = (expected or "").strip()
    if not exp or not fragments:
        return False
    chunks = [c for c in (f.strip() for f in fragments) if c]
    if not chunks:
        return False
    joined = "".join(chunks)
    joined_sp = " ".join(chunks)
    if exp in joined or exp in joined_sp:
        return True
    exp_nw = re.sub(r"\s+", "", exp)
    blob_nw = re.sub(r"\s+", "", joined)
    if exp_nw and exp_nw in blob_nw:
        return True
    return False


def _doh_query_txt(provider: str, url: str, expected: str, timeout_sec: float) -> Optional[Dict[str, Any]]:
    """单次 DNS-over-HTTPS JSON 查询；网络/解析失败返回 None；成功则返回结果 dict（matched 可能为 False）。"""
    try:
        req = Request(
            url,
            headers={"Accept": "application/dns-json", "User-Agent": "nginx-webui/1.0"},
        )
        with urlopen(req, timeout=timeout_sec) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception:
        return None

    status = data.get("Status")
    try:
        st = int(status) if status is not None else 0
    except (TypeError, ValueError):
        st = 0

    # RFC 8482: 2=SERVFAIL 等瞬时错误，换其它 DoH 再试
    if st == 2:
        return None

    answers = data.get("Answer") or []
    txt_values: List[str] = []
    for ans in answers:
        try:
            t = int(ans.get("type", 0))
        except (TypeError, ValueError):
            continue
        if t != 16:
            continue
        txt_values.extend(_split_txt_rr_data(ans.get("data")))

    matched = _txt_expected_matches_found(expected, txt_values)
    if st != 0 and not matched:
        msg = (
            f"DNS 状态 {st}（无匹配 TXT，可能尚未生效或主机名有误）"
            if not txt_values
            else "未在 DNS 响应中找到匹配的 TXT 值"
        )
    else:
        msg = "TXT 记录已匹配" if matched else "未在 DNS 响应中找到匹配的 TXT 值"

    return {
        "success": True,
        "matched": matched,
        "message": msg,
        "checked_with": provider,
        "records": txt_values,
    }


def _names_for_txt_query(record_name: str) -> List[str]:
    n = (record_name or "").strip().strip(".")
    if not n:
        return []
    names = [n, f"{n}."]
    return list(dict.fromkeys(names))


def verify_dns_txt_record(record_name: str, expected_value: str, expected_values: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    检查公网 DNS 是否已包含指定 TXT 值。
    支持多个期望值（通配符证书场景），当 expected_values 非空时逐个检查。
    顺序：DoH（多源、多查询名，直到匹配或全部尝试）→ dig → nslookup。
    """
    expected = (expected_value or "").strip()
    names = _names_for_txt_query(record_name)
    if not names or not expected:
        return {
            "success": False,
            "matched": False,
            "message": "记录名或验证值为空",
            "checked_with": None,
            "records": [],
        }

    # 构建所有期望值的列表
    all_expected: List[str] = []
    if expected_values:
        all_expected = [v.strip() for v in expected_values if v and v.strip()]
    if expected and expected not in all_expected:
        all_expected.insert(0, expected)
    if not all_expected:
        return {
            "success": False,
            "matched": False,
            "message": "记录名或验证值为空",
            "checked_with": None,
            "records": [],
        }

    need_all = len(all_expected) > 1

    last_doh: Optional[Dict[str, Any]] = None

    # 1) DNS-over-HTTPS：同一记录名在多家 DoH 上结果可能不一致，未匹配时继续尝试
    for qname in names:
        for provider, url, tmo in (
            ("CloudflareDoH", f"https://cloudflare-dns.com/dns-query?name={quote(qname)}&type=TXT", 6.0),
            ("AliDNSDoH", f"https://dns.alidns.com/resolve?name={quote(qname)}&type=TXT", 6.0),
            ("GoogleDoH", f"https://dns.google/resolve?name={quote(qname)}&type=TXT", 6.0),
        ):
            if need_all:
                # 多值模式：检查第一个期望值即可获取 TXT 列表，然后自行比对
                got = _doh_query_txt(provider, url, all_expected[0], tmo)
            else:
                got = _doh_query_txt(provider, url, all_expected[0], tmo)
            if got is None:
                continue
            last_doh = got
            found_records = got.get("records", [])
            if need_all:
                # 检查所有期望值是否都存在
                missing = [v for v in all_expected if not _txt_expected_matches_found(v, found_records)]
                if not missing:
                    got["matched"] = True
                    got["message"] = f"全部 {len(all_expected)} 个 TXT 记录均已匹配"
                    return got
                else:
                    got["matched"] = False
                    got["message"] = f"已匹配 {len(all_expected) - len(missing)}/{len(all_expected)} 个 TXT 记录（缺少 {len(missing)} 个）"
            if got.get("matched"):
                return got
    if last_doh is not None:
        return last_doh

    # 2) dig（+time/+tries 限制单次查询时长）
    dig_exe_missing = False
    for qname in names:
        for server in ("223.5.5.5", "114.114.114.114", "8.8.8.8"):
            dig_cmd = [
                "dig",
                "+short",
                "+time=2",
                "+tries=1",
                "TXT",
                qname,
                f"@{server}",
            ]
            try:
                r = subprocess.run(
                    dig_cmd, capture_output=True, text=True, timeout=8
                )
                out = (r.stdout or "") + (r.stderr or "")
                if not out.strip():
                    continue
                chunks = re.findall(r'"([^"]*)"', out)
                if not chunks:
                    chunks = [out.strip()]
                if need_all:
                    missing = [v for v in all_expected if not _txt_expected_matches_found(v, chunks)]
                    matched = len(missing) == 0
                    msg = (
                        f"全部 {len(all_expected)} 个 TXT 记录均已匹配"
                        if matched
                        else f"已匹配 {len(all_expected) - len(missing)}/{len(all_expected)} 个 TXT 记录（缺少 {len(missing)} 个）"
                    )
                else:
                    matched = _txt_expected_matches_found(all_expected[0], chunks)
                    msg = "TXT 记录已匹配" if matched else "未在 DNS 响应中找到匹配的 TXT 值"
                return {
                    "success": True,
                    "matched": matched,
                    "message": msg,
                    "checked_with": " ".join(dig_cmd),
                    "records": chunks,
                }
            except FileNotFoundError:
                dig_exe_missing = True
                break
            except Exception:
                continue
        if dig_exe_missing:
            break

    # 3) nslookup（Windows / 无 dig）
    for qname in names:
        for ns_cmd in (
            ["nslookup", "-type=TXT", qname, "223.5.5.5"],
            ["nslookup", "-type=TXT", qname, "8.8.8.8"],
            ["nslookup", "-type=TXT", qname],
        ):
            try:
                r = subprocess.run(
                    ns_cmd, capture_output=True, text=True, timeout=10
                )
                out = (r.stdout or "") + (r.stderr or "")
                chunks = re.findall(r'"([^"]*)"', out)
                if not chunks:
                    chunks = re.findall(
                        r"(?:text|TXT)\s*=\s*([^\r\n]+)", out, flags=re.IGNORECASE
                    )
                chunks = [c.strip().strip('"') for c in chunks if c and str(c).strip()]
                if need_all:
                    missing = [v for v in all_expected if not _txt_expected_matches_found(v, chunks)]
                    matched = len(missing) == 0 or any(v in out for v in all_expected)
                    msg = (
                        f"全部 {len(all_expected)} 个 TXT 记录均已匹配"
                        if matched
                        else f"已匹配 {len(all_expected) - len(missing)}/{len(all_expected)} 个 TXT 记录"
                    )
                else:
                    matched = _txt_expected_matches_found(all_expected[0], chunks) or (
                        all_expected[0] in out
                    )
                    msg = "TXT 记录已匹配" if matched else "未在 DNS 响应中找到匹配的 TXT 值"
                return {
                    "success": True,
                    "matched": matched,
                    "message": msg,
                    "checked_with": " ".join(ns_cmd),
                    "records": chunks if chunks else [out[:2000]],
                }
            except FileNotFoundError:
                continue
            except Exception:
                continue

    return {
        "success": False,
        "matched": False,
        "message": "DNS 检测失败：DoH、dig、nslookup 均不可用或查询失败",
        "checked_with": None,
        "records": [],
    }


def resolve_certbot_lineage(wildcard_or_domain: str) -> Optional[str]:
    """
    通过 certbot certificates 列表定位包含指定通配符/域名的真实 lineage 名称。
    对每个条目用 openssl 读 SAN 来匹配。
    返回 lineage 名（即 Certificate Name），找不到返回 None。
    """
    for entry in list_certificates():
        name = entry.get("domain") or ""
        cert_path = entry.get("cert_path") or ""
        if not cert_path or not Path(cert_path).is_file():
            continue
        try:
            r = subprocess.run(
                ["openssl", "x509", "-in", cert_path, "-noout", "-ext", "subjectAltName"],
                capture_output=True, text=True, timeout=10,
            )
            san_line = (r.stdout or "") + (r.stderr or "")
        except Exception:
            san_line = ""
        # 匹配 SAN 中的域名（格式：DNS:*.example.com, DNS:example.com）
        if wildcard_or_domain in san_line or wildcard_or_domain == name:
            return name
    return None


def complete_dns_manual_challenge(job_id: str) -> Dict[str, Any]:
    """
    向挂起的 certbot 发送回车，等待签发结束。
    """
    _cleanup_stale_dns_jobs()
    with _dns_jobs_lock:
        job = _dns_jobs.get(job_id)

    if not job:
        return {
            "success": False,
            "message": "无效或已过期的任务 ID，请重新获取 DNS 验证信息",
            "output": "",
            "cert_path": None,
            "key_path": None,
            "domain": None,
            "error_code": "invalid_job",
            "suggestions": ["请从第一步重新发起 DNS 验证流程"],
        }

    proc: subprocess.Popen = job["proc"]
    domain = job["domain"]
    challenge_count = job.get("challenge_count", 1)

    try:
        if proc.stdin:
            # 通配符证书需要多次 Enter（每个 challenge 一次）
            enter_input = "\n" * challenge_count
            proc.stdin.write(enter_input)
            proc.stdin.flush()
            # 关闭 stdin，让 certbot 知道输入结束
            proc.stdin.close()
    except Exception as e:
        return {
            "success": False,
            "message": f"无法继续 certbot 会话: {str(e)}",
            "output": job.get("stdout_tail", ""),
            "cert_path": None,
            "key_path": None,
            "domain": job.get("domain"),
            "error_code": "stdin_error",
            "suggestions": [],
        }

    try:
        # 读取剩余输出直到进程结束
        deadline = time.time() + 300
        remaining_buf: List[str] = []
        assert proc.stdout is not None
        while time.time() < deadline:
            if proc.poll() is not None:
                rest = proc.stdout.read() or ""
                remaining_buf.append(rest)
                break
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.05)
                continue
            remaining_buf.append(line)
        rest_out = "".join(remaining_buf)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        with _dns_jobs_lock:
            popped = _dns_jobs.pop(job_id, None)
        if popped and popped.get("holds_exec_lock"):
            try:
                _certbot_exec_lock.release()
            except RuntimeError:
                pass
        return {
            "success": False,
            "message": "certbot 执行超时",
            "output": job.get("stdout_tail", ""),
            "cert_path": None,
            "key_path": None,
            "domain": job.get("domain"),
            "error_code": "timeout",
            "suggestions": ["检查网络与 Let's Encrypt 连通性", "确认 DNS TXT 已全球生效"],
        }

    full_out = (job.get("stdout_tail") or "") + (rest_out or "")
    success = proc.returncode == 0

    with _dns_jobs_lock:
        popped = _dns_jobs.pop(job_id, None)
    if popped and popped.get("holds_exec_lock"):
        try:
            _certbot_exec_lock.release()
        except RuntimeError:
            pass

    cert_path = None
    key_path = None
    certbot_cert_name = None

    if success:
        # 通过 certbot certificates 列表定位真实 lineage（通配符场景下 lineage 名可能与输入域名不同）
        certbot_cert_name = resolve_certbot_lineage(domain)
        if certbot_cert_name:
            cert_path = str(get_certbot_live_root() / certbot_cert_name / "fullchain.pem")
            key_path = str(get_certbot_live_root() / certbot_cert_name / "privkey.pem")
            if not Path(cert_path).exists():
                cert_path = None
            if not Path(key_path).exists():
                key_path = None
        if not cert_path:
            # 回退：直接用 domain 查找
            cert_path = str(get_certbot_live_root() / domain / "fullchain.pem")
            key_path = str(get_certbot_live_root() / domain / "privkey.pem")
            if not Path(cert_path).exists():
                cert_path = None
            if not Path(key_path).exists():
                key_path = None

    ret: Dict[str, Any] = {
        "success": success,
        "message": "证书申请成功" if success else "证书申请失败",
        "output": full_out,
        "cert_path": cert_path if success else None,
        "key_path": key_path if success else None,
        "domain": domain,
        "email": job.get("email"),
        "certbot_cert_name": certbot_cert_name,
        "_base_domain": job.get("_base_domain"),
    }
    if not success:
        ret = _enrich_failure_result(ret, "dns")
    else:
        ret["error_code"] = None
        ret["suggestions"] = None
    return ret


def verify_certificate_files(cert_path: str, key_path: Optional[str] = None) -> Dict[str, Any]:
    """
    使用 openssl 校验证书文件可读、未过期、与私钥匹配（若提供私钥）。
    """
    cp = Path(cert_path)
    if not cp.exists():
        return {
            "success": False,
            "valid": False,
            "message": f"证书文件不存在: {cert_path}",
            "details": {},
        }

    details: Dict[str, Any] = {}
    try:
        r = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(cp),
                "-noout",
                "-checkend",
                "0",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        not_expired = r.returncode == 0
        details["not_expired"] = not_expired
        if r.returncode != 0:
            details["checkend_stderr"] = (r.stderr or "")[:500]

        info = get_certificate_info(str(cp))
        details["issuer"] = info.get("issuer")
        details["domain"] = info.get("domain")
        details["valid_to"] = info.get("valid_to")
        details["valid_from"] = info.get("valid_from")

        key_ok = True
        if key_path and Path(key_path).exists():
            r_pub = subprocess.run(
                [
                    "openssl",
                    "x509",
                    "-noout",
                    "-pubkey",
                    "-in",
                    str(cp),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            r_key = subprocess.run(
                [
                    "openssl",
                    "pkey",
                    "-pubout",
                    "-in",
                    str(key_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if r_pub.returncode == 0 and r_key.returncode == 0:
                key_ok = (r_pub.stdout or "").strip() == (r_key.stdout or "").strip()
            else:
                key_ok = False
            details["key_matches_cert"] = key_ok
        else:
            details["key_matches_cert"] = None

        valid = bool(
            not_expired
            and info.get("success")
            and (details["key_matches_cert"] is not False)
        )
        return {
            "success": True,
            "valid": valid,
            "message": "证书校验通过" if valid else "证书存在问题（未过期/信息/密钥匹配项未全部满足）",
            "details": details,
        }
    except Exception as e:
        return {
            "success": False,
            "valid": False,
            "message": f"校验过程异常: {str(e)}",
            "details": details,
        }


def test_auto_renew_environment() -> Dict[str, Any]:
    """
    检测当前环境是否具备自动续签能力：certbot/openssl、已管理证书数量、
    执行 `certbot renew --dry-run` 验证 ACME 续签链路（不修改真实证书）。
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)
    letsencrypt_root = get_certbot_config_dir()
    checks: List[Dict[str, Any]] = []

    def add_check(
        check_id: str, ok: bool, label: str, detail: str
    ) -> None:
        checks.append(
            {"id": check_id, "ok": ok, "label": label, "detail": detail}
        )

    if not certbot_path.exists():
        add_check(
            "certbot_binary",
            False,
            "Certbot 可执行文件",
            f"路径不存在: {certbot_path}",
        )
        return {
            "success": False,
            "environment_ready": False,
            "summary": "未找到 certbot，无法进行自动续签",
            "checks": checks,
            "lineage_count": 0,
            "dry_run_output": "",
            "error_code": "certbot_missing",
            "suggestions": [
                "安装 certbot 并在配置中设置 nginx.certbot_path",
                "Docker 部署时需镜像内包含 certbot 或挂载可执行文件",
            ],
        }

    if not os.access(certbot_path, os.X_OK):
        add_check(
            "certbot_binary",
            False,
            "Certbot 可执行文件",
            f"文件存在但不可执行: {certbot_path}",
        )
        return {
            "success": False,
            "environment_ready": False,
            "summary": "certbot 不可执行",
            "checks": checks,
            "lineage_count": 0,
            "dry_run_output": "",
            "error_code": "certbot_not_executable",
            "suggestions": ["检查文件权限", "确认配置路径指向正确的 certbot"],
        }

    add_check(
        "certbot_binary",
        True,
        "Certbot 可执行文件",
        str(certbot_path.resolve()),
    )

    try:
        r = subprocess.run(
            ["openssl", "version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        openssl_ok = r.returncode == 0
        ver = (r.stdout or r.stderr or "").strip()[:120]
        add_check(
            "openssl",
            openssl_ok,
            "OpenSSL",
            ver if ver else "无法获取版本信息",
        )
    except FileNotFoundError:
        add_check("openssl", False, "OpenSSL", "未找到 openssl 命令")
    except Exception as e:
        add_check("openssl", False, "OpenSSL", f"检测异常: {e}")

    le_exists = letsencrypt_root.is_dir()
    add_check(
        "letsencrypt_dir",
        True,
        "Certbot 证书目录",
        (
            f"存在：{letsencrypt_root}"
            if le_exists
            else "不存在（Windows 或未使用默认路径时常见；certbot 仍可能正常工作）"
        ),
    )

    lineages = list_certificates()
    lineage_count = len(lineages)
    add_check(
        "lineages",
        True,
        "Certbot 已管理证书",
        f"共 {lineage_count} 个 lineage（无则 dry-run 仍会验证环境）",
    )

    try:
        dry = _run_certbot(
            [
                str(certbot_path),
                "renew",
                "--config-dir",
                str(letsencrypt_root),
                "--dry-run",
                "--non-interactive",
            ],
            timeout=300,
        )
        if dry.get("timed_out"):
            add_check(
                "dry_run",
                False,
                "续签模拟（dry-run）",
                "执行超时（300 秒）",
            )
            return {
                "success": False,
                "environment_ready": False,
                "summary": "模拟续签超时",
                "checks": checks,
                "lineage_count": lineage_count,
                "dry_run_output": "",
                "error_code": "timeout",
                "suggestions": ["检查网络与 Let’s Encrypt 连通性", "证书较多时可稍后重试"],
            }
        if dry.get("error_code") == "certbot_busy":
            add_check(
                "dry_run",
                False,
                "续签模拟（dry-run）",
                "有其他 certbot 任务正在执行",
            )
            return {
                "success": False,
                "environment_ready": False,
                "summary": "Certbot 正在被其他任务占用",
                "checks": checks,
                "lineage_count": lineage_count,
                "dry_run_output": "",
                "error_code": "certbot_busy",
                "suggestions": ["等待当前 certbot 操作完成后重试"],
            }

        out = dry.get("output", "")
        dry_ok = bool(dry.get("success"))
        if dry_ok:
            add_check(
                "dry_run",
                True,
                "续签模拟（dry-run）",
                "通过：ACME 续签链路可用（未修改真实证书）",
            )
            summary = (
                "环境支持自动续签：模拟续签成功。"
                if lineage_count
                else "环境可用：当前无 Certbot 证书 lineage，模拟续签已通过（申请证书后定时任务将执行 renew）。"
            )
            return {
                "success": True,
                "environment_ready": True,
                "summary": summary,
                "checks": checks,
                "lineage_count": lineage_count,
                "dry_run_output": out[-8000:] if len(out) > 8000 else out,
                "error_code": None,
                "suggestions": None,
            }

        add_check(
            "dry_run",
            False,
            "续签模拟（dry-run）",
            "失败：请查看下方输出",
        )
        enriched = _enrich_failure_result(
            {"success": False, "message": "证书续期失败", "output": out},
            "http",
        )
        return {
            "success": False,
            "environment_ready": False,
            "summary": enriched.get("message") or "模拟续签失败",
            "checks": checks,
            "lineage_count": lineage_count,
            "dry_run_output": out[-8000:] if len(out) > 8000 else out,
            "error_code": enriched.get("error_code"),
            "suggestions": enriched.get("suggestions"),
        }
    except Exception as e:
        add_check(
            "dry_run",
            False,
            "续签模拟（dry-run）",
            str(e),
        )
        return {
            "success": False,
            "environment_ready": False,
            "summary": f"模拟续签异常: {e}",
            "checks": checks,
            "lineage_count": lineage_count,
            "dry_run_output": "",
            "error_code": "exception",
            "suggestions": [str(e)],
        }


def renew_certificate(domain: Optional[str] = None) -> Dict[str, Any]:
    """
    续期证书

    Args:
        domain: 域名（如果为 None，则续期所有证书）

    Returns:
        {
            "success": bool,
            "message": str,
            "output": str,
            error_code, suggestions (失败时)
        }
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)

    if not certbot_path.exists():
        return {
            "success": False,
            "message": f"Certbot 可执行文件不存在: {certbot_path}",
            "output": "",
            "error_code": "certbot_missing",
            "suggestions": ["安装 certbot 并配置路径"],
        }

    cmd = [
        str(certbot_path),
        "renew",
        "--config-dir",
        str(get_certbot_config_dir()),
        "--non-interactive",
    ]

    if domain:
        cmd.extend(["--cert-name", domain])

    try:
        result = _run_certbot(cmd, timeout=300)
        if result.get("timed_out"):
            return {
                "success": False,
                "message": "证书续期超时",
                "output": "",
                "error_code": "timeout",
                "suggestions": [],
            }
        if result.get("error_code") == "certbot_busy":
            return {
                "success": False,
                "message": "Certbot 正在被其他任务占用，请稍后重试",
                "output": "",
                "error_code": "certbot_busy",
                "suggestions": ["等待 10-30 秒后重试"],
            }

        success = bool(result.get("success"))
        output = result.get("output", "")
        ret: Dict[str, Any] = {
            "success": success,
            "message": "证书续期成功" if success else "证书续期失败",
            "output": output,
        }
        if not success:
            ret = _enrich_failure_result(ret, "http")
        else:
            ret["error_code"] = None
            ret["suggestions"] = None
        return ret
    except Exception as e:
        return {
            "success": False,
            "message": f"证书续期出错: {str(e)}",
            "output": "",
            "error_code": "exception",
            "suggestions": [str(e)],
        }


def list_certificates() -> List[Dict[str, str]]:
    """
    列出所有已申请的证书

    Returns:
        List[Dict]: 证书列表，每个证书包含 domain, cert_path, key_path
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)

    if not certbot_path.exists():
        return []

    try:
        result = _run_certbot(
            [
                str(certbot_path),
                "certificates",
                "--config-dir",
                str(get_certbot_config_dir()),
            ],
            timeout=30,
            cleanup_lock=False,
        )

        if not result.get("success"):
            return []

        # 解析输出
        certificates = []
        lines = (result.get("stdout") or "").split("\n")

        for line in lines:
            # 查找证书名称和路径
            if "Certificate Name:" in line:
                match = re.search(r"Certificate Name:\s+(\S+)", line)
                if match:
                    domain = match.group(1)
                    # 默认路径
                    cert_path = str(get_certbot_live_root() / domain / "fullchain.pem")
                    key_path = str(get_certbot_live_root() / domain / "privkey.pem")

                    certificates.append(
                        {
                            "domain": domain,
                            "cert_path": cert_path,
                            "key_path": key_path,
                        }
                    )

        return certificates
    except Exception:
        return []


def get_certificate_info(cert_path: str) -> Dict[str, Any]:
    """
    获取证书信息（域名、过期时间等）

    Args:
        cert_path: 证书文件路径

    Returns:
        {
            "domain": Optional[str],
            "issuer": Optional[str],
            "valid_from": Optional[datetime],
            "valid_to": Optional[datetime],
            "success": bool
        }
    """
    cert_file = Path(cert_path)

    if not cert_file.exists():
        return {
            "success": False,
            "domain": None,
            "issuer": None,
            "valid_from": None,
            "valid_to": None,
        }

    try:
        # 使用 openssl 读取证书信息
        result = subprocess.run(
            [
                "openssl",
                "x509",
                "-in",
                str(cert_file),
                "-noout",
                "-text",
                "-dates",
                "-issuer",
                "-subject",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            return {
                "success": False,
                "domain": None,
                "issuer": None,
                "valid_from": None,
                "valid_to": None,
            }

        output = result.stdout

        # 解析域名
        domain_match = re.search(r"CN\s*=\s*([^\s,]+)", output)
        domain = domain_match.group(1) if domain_match else None

        # 解析颁发者
        issuer_match = re.search(r"Issuer:\s*(.+)", output)
        issuer = issuer_match.group(1).strip() if issuer_match else None

        # 解析有效期
        valid_from = None
        valid_to = None

        not_before_match = re.search(r"notBefore=(.+)", output)
        not_after_match = re.search(r"notAfter=(.+)", output)

        if not_before_match:
            try:
                valid_from = datetime.strptime(
                    not_before_match.group(1).strip(),
                    "%b %d %H:%M:%S %Y %Z",
                )
            except ValueError:
                pass

        if not_after_match:
            try:
                valid_to = datetime.strptime(
                    not_after_match.group(1).strip(),
                    "%b %d %H:%M:%S %Y %Z",
                )
            except ValueError:
                pass

        return {
            "success": True,
            "domain": domain,
            "issuer": issuer,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_to": valid_to.isoformat() if valid_to else None,
        }
    except Exception as e:
        return {
            "success": False,
            "domain": None,
            "issuer": None,
            "valid_from": None,
            "valid_to": None,
            "error": str(e),
        }
