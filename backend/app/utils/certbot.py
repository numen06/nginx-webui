"""
Certbot 工具封装
"""
import subprocess
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.config import get_config


def copy_certificate_files(domain: str) -> Dict[str, Any]:
    """
    从 certbot 默认路径复制证书文件到项目的 ssl_dir

    Args:
        domain: 域名

    Returns:
        {
            "success": bool,
            "message": str,
            "cert_path": Optional[str],
            "key_path": Optional[str]
        }
    """
    config = get_config()

    # certbot 默认路径
    certbot_live_dir = Path("/etc/letsencrypt/live") / domain
    source_cert = certbot_live_dir / "fullchain.pem"
    source_key = certbot_live_dir / "privkey.pem"

    # 检查源文件是否存在
    if not source_cert.exists():
        return {
            "success": False,
            "message": f"Certbot 证书文件不存在: {source_cert}",
            "cert_path": None,
            "key_path": None
        }

    if not source_key.exists():
        return {
            "success": False,
            "message": f"Certbot 私钥文件不存在: {source_key}",
            "cert_path": None,
            "key_path": None
        }

    # 目标路径（项目的 ssl_dir）
    ssl_dir = Path(config.nginx.ssl_dir)
    ssl_dir.mkdir(parents=True, exist_ok=True)

    target_cert = ssl_dir / f"{domain}.crt"
    target_key = ssl_dir / f"{domain}.key"

    try:
        # 复制证书文件
        shutil.copy2(source_cert, target_cert)
        shutil.copy2(source_key, target_key)

        # 确保目标路径是绝对路径
        target_cert_abs = target_cert.resolve()
        target_key_abs = target_key.resolve()

        return {
            "success": True,
            "message": "证书文件复制成功",
            "cert_path": str(target_cert_abs),
            "key_path": str(target_key_abs)
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"复制证书文件失败: {str(e)}",
            "cert_path": None,
            "key_path": None
        }



def request_certificate(
    domains: List[str],
    email: str,
    validation_method: str = "http"
) -> Dict[str, Any]:
    """
    通过 certbot 申请证书
    
    Args:
        domains: 域名列表
        email: 邮箱地址
        validation_method: 验证方式 ('http' 或 'dns')
    
    Returns:
        {
            "success": bool,
            "message": str,
            "output": str,
            "cert_path": Optional[str],
            "key_path": Optional[str]
        }
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)
    
    if not certbot_path.exists():
        return {
            "success": False,
            "message": f"Certbot 可执行文件不存在: {certbot_path}",
            "output": "",
            "cert_path": None,
            "key_path": None
        }
    
    # 构建 certbot 命令
    cmd = [
        str(certbot_path),
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--email", email,
        "--expand"
    ]
    
    # 添加域名
    for domain in domains:
        cmd.extend(["-d", domain])
    
    # 验证方式
    if validation_method == "http":
        cmd.append("--webroot")
        cmd.extend(["--webroot-path", str(Path(config.nginx.static_dir))])
    elif validation_method == "dns":
        cmd.append("--manual")
        cmd.append("--preferred-challenges", "dns")
    else:
        return {
            "success": False,
            "message": f"不支持的验证方式: {validation_method}",
            "output": "",
            "cert_path": None,
            "key_path": None
        }
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        success = result.returncode == 0
        
        # 解析证书路径
        cert_path = None
        key_path = None
        
        if success and domains:
            # 默认证书路径：/etc/letsencrypt/live/{domain}/fullchain.pem
            domain = domains[0]
            cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
            key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"
            
            # 验证路径是否存在
            if not Path(cert_path).exists():
                cert_path = None
            if not Path(key_path).exists():
                key_path = None
        
        return {
            "success": success,
            "message": "证书申请成功" if success else "证书申请失败",
            "output": result.stdout + result.stderr,
            "cert_path": cert_path,
            "key_path": key_path
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "证书申请超时",
            "output": "",
            "cert_path": None,
            "key_path": None
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"证书申请出错: {str(e)}",
            "output": "",
            "cert_path": None,
            "key_path": None
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
            "output": str
        }
    """
    config = get_config()
    certbot_path = Path(config.nginx.certbot_path)
    
    if not certbot_path.exists():
        return {
            "success": False,
            "message": f"Certbot 可执行文件不存在: {certbot_path}",
            "output": ""
        }
    
    cmd = [
        str(certbot_path),
        "renew",
        "--non-interactive"
    ]
    
    if domain:
        cmd.extend(["--cert-name", domain])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        success = result.returncode == 0
        
        return {
            "success": success,
            "message": "证书续期成功" if success else "证书续期失败",
            "output": result.stdout + result.stderr
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "证书续期超时",
            "output": ""
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"证书续期出错: {str(e)}",
            "output": ""
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
        result = subprocess.run(
            [str(certbot_path), "certificates"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            return []
        
        # 解析输出
        certificates = []
        lines = result.stdout.split('\n')
        
        for line in lines:
            # 查找证书名称和路径
            if 'Certificate Name:' in line:
                match = re.search(r'Certificate Name:\s+(\S+)', line)
                if match:
                    domain = match.group(1)
                    # 默认路径
                    cert_path = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
                    key_path = f"/etc/letsencrypt/live/{domain}/privkey.pem"
                    
                    certificates.append({
                        "domain": domain,
                        "cert_path": cert_path,
                        "key_path": key_path
                    })
        
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
            "valid_to": None
        }
    
    try:
        # 使用 openssl 读取证书信息
        result = subprocess.run(
            [
                "openssl", "x509",
                "-in", str(cert_file),
                "-noout",
                "-text",
                "-dates",
                "-issuer",
                "-subject"
            ],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return {
                "success": False,
                "domain": None,
                "issuer": None,
                "valid_from": None,
                "valid_to": None
            }
        
        output = result.stdout
        
        # 解析域名
        domain_match = re.search(r'CN\s*=\s*([^\s,]+)', output)
        domain = domain_match.group(1) if domain_match else None
        
        # 解析颁发者
        issuer_match = re.search(r'Issuer:\s*(.+)', output)
        issuer = issuer_match.group(1).strip() if issuer_match else None
        
        # 解析有效期
        valid_from = None
        valid_to = None
        
        not_before_match = re.search(r'notBefore=(.+)', output)
        not_after_match = re.search(r'notAfter=(.+)', output)
        
        if not_before_match:
            try:
                valid_from = datetime.strptime(
                    not_before_match.group(1).strip(),
                    "%b %d %H:%M:%S %Y %Z"
                )
            except ValueError:
                pass
        
        if not_after_match:
            try:
                valid_to = datetime.strptime(
                    not_after_match.group(1).strip(),
                    "%b %d %H:%M:%S %Y %Z"
                )
            except ValueError:
                pass
        
        return {
            "success": True,
            "domain": domain,
            "issuer": issuer,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_to": valid_to.isoformat() if valid_to else None
        }
    except Exception as e:
        return {
            "success": False,
            "domain": None,
            "issuer": None,
            "valid_from": None,
            "valid_to": None,
            "error": str(e)
        }

