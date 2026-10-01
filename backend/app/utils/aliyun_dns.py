"""Aliyun DNS-01 credentials and Certbot manual authentication hooks.

Run as ``python /app/backend/app/utils/aliyun_dns.py auth|cleanup`` from
Certbot. Credentials are kept in the persistent data directory, never in a
Certbot renewal file or an API response.
"""

import json
import os
import re
import socket
import sys
import tempfile
import time
import secrets
from pathlib import Path
from typing import Dict, Optional


_ZONE_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}$")
_RECORD_ID_RE = re.compile(r"^[0-9]+$")


def credentials_path() -> Path:
    return Path(os.environ.get("DATA_ROOT", "/app/data")) / "letsencrypt" / "aliyun-dns.json"


def load_credentials() -> Optional[Dict[str, str]]:
    path = credentials_path()
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not all(data.get(k) for k in ("zone", "access_key_id", "access_key_secret")):
        return None
    return data


def save_credentials(zone: str, access_key_id: str, access_key_secret: str) -> None:
    zone = zone.strip().lower().rstrip(".")
    if not _ZONE_RE.fullmatch(zone):
        raise ValueError("DNS 主域名格式不正确")
    if not access_key_id.strip() or not access_key_secret.strip():
        raise ValueError("AccessKey ID 和 Secret 不能为空")
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".aliyun-dns-", dir=str(path.parent))
    try:
        os.chmod(temp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({
                "zone": zone,
                "access_key_id": access_key_id.strip(),
                "access_key_secret": access_key_secret.strip(),
            }, stream)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _client(credentials: Dict[str, str]):
    from aliyunsdkcore.client import AcsClient

    return AcsClient(credentials["access_key_id"], credentials["access_key_secret"], "cn-hangzhou")


def test_credentials(credentials: Dict[str, str]) -> None:
    from aliyunsdkalidns.request.v20150109.DescribeDomainRecordsRequest import (
        DescribeDomainRecordsRequest,
    )

    request = DescribeDomainRecordsRequest()
    request.set_protocol_type("https")
    request.set_DomainName(credentials["zone"])
    request.set_PageSize(1)
    _client(credentials).do_action_with_exception(request)

    # Check the exact permissions renewal needs, using an isolated probe record.
    name = "_acme-challenge-probe." + credentials["zone"]
    record_id = _add_txt(credentials, name, secrets.token_urlsafe(18))
    _delete_txt(credentials, record_id)


def _record_name(identifier: str, zone: str) -> str:
    domain = identifier.strip().lower().removeprefix("*.").rstrip(".")
    if not _ZONE_RE.fullmatch(domain):
        raise ValueError("申请域名格式不正确")
    if domain != zone and not domain.endswith("." + zone):
        raise ValueError("申请域名不属于已配置的阿里云 DNS 主域名")
    prefix = "" if domain == zone else domain[: -(len(zone) + 1)] + "."
    return "_acme-challenge." + prefix + zone


def _add_txt(credentials: Dict[str, str], name: str, value: str) -> str:
    from aliyunsdkalidns.request.v20150109.AddDomainRecordRequest import (
        AddDomainRecordRequest,
    )

    zone = credentials["zone"]
    request = AddDomainRecordRequest()
    request.set_protocol_type("https")
    request.set_DomainName(zone)
    request.set_RR(name[: -(len(zone) + 1)])
    request.set_Type("TXT")
    request.set_Value(value)
    request.set_TTL(600)
    response = json.loads(_client(credentials).do_action_with_exception(request))
    record_id = str(response.get("RecordId") or "")
    if not _RECORD_ID_RE.fullmatch(record_id):
        raise RuntimeError("阿里云 DNS 未返回有效的记录 ID")
    return record_id


def _delete_txt(credentials: Dict[str, str], record_id: str) -> None:
    from aliyunsdkalidns.request.v20150109.DeleteDomainRecordRequest import (
        DeleteDomainRecordRequest,
    )

    if not _RECORD_ID_RE.fullmatch(record_id):
        raise ValueError("无效的 DNS 记录 ID")
    request = DeleteDomainRecordRequest()
    request.set_protocol_type("https")
    request.set_RecordId(record_id)
    _client(credentials).do_action_with_exception(request)


def _wait_for_txt(name: str, value: str, zone: str, seconds: int = 300) -> bool:
    # Public recursive resolvers may cache a previous TXT value for its full
    # TTL. Let's Encrypt ultimately needs the authoritative nameservers to
    # have the new value, so query each of them directly.
    import dns.resolver

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            nameservers = [str(item.target).rstrip(".") for item in dns.resolver.resolve(zone, "NS", lifetime=5)]
            if nameservers:
                matches = []
                for nameserver in nameservers:
                    query = dns.resolver.Resolver(configure=False)
                    query.nameservers = [socket.gethostbyname(nameserver)]
                    query.timeout = 3
                    query.lifetime = 5
                    records = query.resolve(name, "TXT", lifetime=5)
                    values = [b"".join(record.strings).decode("utf-8") for record in records]
                    matches.append(value in values)
                if all(matches):
                    time.sleep(15)
                    return True
        except (OSError, dns.exception.DNSException, UnicodeError):
            pass
        time.sleep(5)
    return False


def run_hook(action: str) -> None:
    credentials = load_credentials()
    if not credentials:
        raise RuntimeError("尚未在证书 DNS 配置页面保存阿里云凭据")
    if action == "auth":
        identifier = os.environ.get("CERTBOT_DOMAIN") or os.environ.get("CERTBOT_IDENTIFIER", "")
        value = os.environ.get("CERTBOT_VALIDATION", "")
        if not identifier or not value:
            raise RuntimeError("Certbot 未提供 DNS 验证域名或验证值")
        name = _record_name(identifier, credentials["zone"])
        record_id = _add_txt(credentials, name, value)
        try:
            if not _wait_for_txt(name, value, credentials["zone"]):
                raise RuntimeError("阿里云 TXT 已创建，但权威 DNS 在 5 分钟内未生效")
        except Exception:
            _delete_txt(credentials, record_id)
            raise
        print(record_id)
    elif action == "cleanup":
        record_id = os.environ.get("CERTBOT_AUTH_OUTPUT", "").strip()
        if record_id:
            _delete_txt(credentials, record_id)
    else:
        raise ValueError("未知的 DNS hook 操作")


if __name__ == "__main__":
    try:
        run_hook(sys.argv[1] if len(sys.argv) > 1 else "")
    except Exception as exc:
        print(f"阿里云 DNS 验证失败: {exc}", file=sys.stderr)
        sys.exit(1)
