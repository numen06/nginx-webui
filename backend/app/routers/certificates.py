"""
证书管理路由
"""

import shutil
import tarfile
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, List, Tuple
from datetime import datetime
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
    Query,
    Request,
)
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.models import Certificate
from app.utils.certbot import (
    request_certificate,
    renew_certificate,
    list_certificates,
    get_certificate_info,
)
from app.utils.audit import create_audit_log, get_client_ip

router = APIRouter(prefix="/api/certificates", tags=["certificates"])


class CertificateRequest(BaseModel):
    """证书申请请求"""

    domains: List[str]
    email: EmailStr
    validation_method: str = "http"  # 'http' 或 'dns'


class CertificateUpdateRequest(BaseModel):
    """证书更新请求"""

    auto_renew: Optional[bool] = None


CERT_EXTENSIONS = {".crt", ".cer", ".pem"}
KEY_EXTENSIONS = {".key", ".pem"}


def _extract_domain_from_filename(file_path: Path) -> Optional[str]:
    """
    从文件名中提取域名
    常见格式：example.com.crt, example_com.crt, example-com.crt 等
    """
    import re

    stem = file_path.stem  # 不含扩展名的文件名

    # 移除常见的证书文件名前缀/后缀
    # 如：fullchain, cert, certificate, server, client 等
    patterns_to_remove = [
        r"^fullchain[-_]?",
        r"^cert[-_]?",
        r"^certificate[-_]?",
        r"^server[-_]?",
        r"^client[-_]?",
        r"[-_]?fullchain$",
        r"[-_]?cert$",
        r"[-_]?certificate$",
        r"[-_]?server$",
        r"[-_]?client$",
    ]

    cleaned = stem
    for pattern in patterns_to_remove:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # 域名正则：字母数字、点、连字符，至少包含一个点
    domain_pattern = r"^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+)$"

    # 尝试匹配整个文件名
    match = re.match(domain_pattern, cleaned)
    if match:
        return match.group(1)

    # 尝试从文件名中提取域名部分（可能包含下划线或连字符）
    # 例如：example_com.crt -> example.com
    domain_candidate = cleaned.replace("_", ".").replace("-", ".")
    match = re.match(domain_pattern, domain_candidate)
    if match:
        return match.group(1)

    # 尝试提取看起来像域名的部分
    # 匹配包含至少一个点的部分
    domain_match = re.search(
        r"([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)+)",
        cleaned,
    )
    if domain_match:
        candidate = domain_match.group(1)
        # 验证是否为有效域名格式
        if re.match(domain_pattern, candidate):
            return candidate

    return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def _get_file_extension(filename: str, default_ext: str) -> str:
    """从文件名提取扩展名，如果无效则返回默认扩展名"""
    if not filename:
        return default_ext
    ext = Path(filename).suffix.lower()
    # 只接受常见的证书/私钥扩展名
    valid_cert_exts = {".crt", ".pem", ".cer"}
    valid_key_exts = {".key", ".pem"}
    if default_ext == ".crt" and ext in valid_cert_exts:
        return ext
    elif default_ext == ".key" and ext in valid_key_exts:
        return ext
    return default_ext


def _persist_certificate_record(
    *,
    domain: str,
    cert_bytes: bytes,
    key_bytes: bytes,
    auto_renew: bool,
    current_user: User,
    db: Session,
    request: Request,
    audit_action: str,
    success_message: str = "证书上传成功",
    cert_id: Optional[int] = None,  # 如果提供，则更新现有证书
    cert_filename: Optional[str] = None,  # 原始证书文件名
    key_filename: Optional[str] = None,  # 原始私钥文件名
):
    if not cert_bytes or not key_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="证书或私钥内容为空"
        )

    # 域名唯一性校验（在写入文件前检查）
    if cert_id:
        # 更新证书时，检查域名是否变更，如果变更则检查新域名是否已存在
        cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
        if not cert:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在"
            )
        if cert.domain != domain:
            existing_cert = db.query(Certificate).filter(
                Certificate.domain == domain,
                Certificate.id != cert_id
            ).first()
            if existing_cert:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"域名 {domain} 已存在其他证书，无法修改"
                )
    else:
        # 创建新证书时，检查域名是否已存在
        existing_cert = db.query(Certificate).filter(Certificate.domain == domain).first()
        if existing_cert:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"域名 {domain} 已存在证书，请使用重新上传功能更新现有证书"
            )

    config = get_config()
    ssl_dir = Path(config.nginx.ssl_dir)
    # 确保 ssl_dir 是绝对路径
    if not ssl_dir.is_absolute():
        ssl_dir = ssl_dir.resolve()
    ssl_dir.mkdir(parents=True, exist_ok=True)

    # 从原始文件名提取扩展名，保留用户的文件格式
    cert_ext = _get_file_extension(cert_filename, ".crt")
    key_ext = _get_file_extension(key_filename, ".key")
    
    cert_path = ssl_dir / f"{domain}{cert_ext}"
    key_path = ssl_dir / f"{domain}{key_ext}"

    cert_path.write_bytes(cert_bytes)
    key_path.write_bytes(key_bytes)

    # 确保路径是绝对路径
    cert_path_abs = cert_path.resolve()
    key_path_abs = key_path.resolve()

    cert_info = get_certificate_info(str(cert_path_abs)) or {}
    valid_from = _parse_iso_datetime(cert_info.get("valid_from"))
    valid_to = _parse_iso_datetime(cert_info.get("valid_to"))

    # 如果提供了cert_id，更新现有证书；否则创建新证书
    if cert_id:
        # cert 已经在前面查询过了
        if cert.domain != domain:
            cert.domain = domain
        
        # 如果文件路径发生变化（扩展名不同），删除旧文件
        old_cert_path = Path(cert.cert_path) if cert.cert_path else None
        old_key_path = Path(cert.key_path) if cert.key_path else None
        
        # 更新证书信息
        cert.cert_path = str(cert_path_abs)
        cert.key_path = str(key_path_abs)
        
        # 删除旧文件（如果路径不同）
        if old_cert_path and old_cert_path.exists() and old_cert_path != cert_path_abs:
            try:
                old_cert_path.unlink()
            except Exception:
                pass  # 忽略删除失败
        
        if old_key_path and old_key_path.exists() and old_key_path != key_path_abs:
            try:
                old_key_path.unlink()
            except Exception:
                pass  # 忽略删除失败
        cert.issuer = cert_info.get("issuer")
        cert.valid_from = valid_from
        cert.valid_to = valid_to
        cert.auto_renew = auto_renew
        db.commit()
        db.refresh(cert)
        success_message = "证书更新成功"
    else:
        cert = Certificate(
            domain=domain,
            cert_path=str(cert_path_abs),
            key_path=str(key_path_abs),
            issuer=cert_info.get("issuer"),
            valid_from=valid_from,
            valid_to=valid_to,
            auto_renew=auto_renew,
            created_by_id=current_user.id,
        )
        db.add(cert)
        db.commit()
        db.refresh(cert)

    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action=audit_action,
        target=domain,
        details={"cert_path": str(cert_path), "key_path": str(key_path)},
        ip_address=get_client_ip(request),
    )

    return {
        "success": True,
        "message": success_message,
        "certificate": {
            "id": cert.id,
            "domain": cert.domain,
            "cert_path": cert.cert_path,
            "key_path": cert.key_path,
        },
    }


def _classify_pem_file(file_path: Path) -> Optional[str]:
    try:
        content = file_path.read_text(errors="ignore")
    except Exception:
        return None
    if "PRIVATE KEY" in content:
        return "key"
    if "BEGIN CERTIFICATE" in content:
        return "cert"
    return None


def _discover_cert_and_key(
    root_dir: Path, domain: str
) -> Tuple[Optional[Path], Optional[Path]]:
    cert_candidates: List[Path] = []
    key_candidates: List[Path] = []

    for file in root_dir.rglob("*"):
        if not file.is_file():
            continue
        suffix = file.suffix.lower()
        role = None
        if suffix in (CERT_EXTENSIONS - {".pem"}):
            role = "cert"
        elif suffix in (KEY_EXTENSIONS - {".pem"}):
            role = "key"
        elif suffix == ".pem":
            role = _classify_pem_file(file)

        if role == "cert":
            cert_candidates.append(file)
        elif role == "key":
            key_candidates.append(file)

    def pick_candidate(candidates: List[Path]) -> Optional[Path]:
        if not candidates:
            return None
        domain_matches = [c for c in candidates if domain and domain in c.stem]
        if domain_matches:
            return domain_matches[0]
        return candidates[0]

    return pick_candidate(cert_candidates), pick_candidate(key_candidates)


def _ensure_within_dir(path: Path, target_dir: Path):
    resolved_target = target_dir.resolve()
    resolved_path = path.resolve()
    if not str(resolved_path).startswith(str(resolved_target)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="压缩包包含非法路径，已拒绝处理",
        )


def _safe_extract_zip(archive_path: Path, target_dir: Path):
    with zipfile.ZipFile(archive_path) as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue
            member_path = Path(target_dir, member.filename)
            _ensure_within_dir(member_path, target_dir)
            member_path.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(member) as source, open(member_path, "wb") as dest:
                shutil.copyfileobj(source, dest)


def _safe_extract_tar(archive_path: Path, target_dir: Path):
    with tarfile.open(archive_path) as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            member_path = Path(target_dir, member.name)
            _ensure_within_dir(member_path, target_dir)
            member_path.parent.mkdir(parents=True, exist_ok=True)
            extracted = tf.extractfile(member)
            if extracted is None:
                continue
            with open(member_path, "wb") as dest:
                shutil.copyfileobj(extracted, dest)


def _extract_archive(archive_path: Path, target_dir: Path):
    if zipfile.is_zipfile(archive_path):
        _safe_extract_zip(archive_path, target_dir)
        return

    if tarfile.is_tarfile(archive_path):
        _safe_extract_tar(archive_path, target_dir)
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 zip 或 tar 格式的压缩包"
    )


@router.get("", summary="获取证书列表")
async def get_certificates(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取所有证书列表"""
    certificates = db.query(Certificate).order_by(Certificate.created_at.desc()).all()

    result = []
    for cert in certificates:
        # 检查证书是否即将过期（30天内）
        days_until_expiry = None
        if cert.valid_to:
            days_until_expiry = (cert.valid_to - datetime.now()).days

        result.append(
            {
                "id": cert.id,
                "domain": cert.domain,
                "cert_path": cert.cert_path,
                "key_path": cert.key_path,
                "issuer": cert.issuer,
                "valid_from": cert.valid_from.isoformat() if cert.valid_from else None,
                "valid_to": cert.valid_to.isoformat() if cert.valid_to else None,
                "auto_renew": cert.auto_renew,
                "days_until_expiry": days_until_expiry,
                "created_at": cert.created_at.isoformat() if cert.created_at else None,
            }
        )

    return {"success": True, "certificates": result}


@router.get("/{cert_id}", summary="获取证书详情")
async def get_certificate(
    cert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取证书详情"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()

    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在")

    # 重新获取证书信息（可能已更新）
    cert_info = get_certificate_info(cert.cert_path)

    return {
        "success": True,
        "certificate": {
            "id": cert.id,
            "domain": cert.domain,
            "cert_path": cert.cert_path,
            "key_path": cert.key_path,
            "issuer": cert.issuer or cert_info.get("issuer"),
            "valid_from": (
                cert.valid_from.isoformat()
                if cert.valid_from
                else cert_info.get("valid_from")
            ),
            "valid_to": (
                cert.valid_to.isoformat()
                if cert.valid_to
                else cert_info.get("valid_to")
            ),
            "auto_renew": cert.auto_renew,
            "created_at": cert.created_at.isoformat() if cert.created_at else None,
        },
    }


@router.post("/upload", summary="手动上传证书")
async def upload_certificate(
    request: Request,
    domain: str = Form(...),
    cert_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    auto_renew: bool = Form(False),
    cert_id: Optional[int] = Form(None),  # 如果提供，则更新现有证书
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动上传证书（如果提供cert_id，则更新现有证书）"""
    try:
        cert_bytes = await cert_file.read()
        key_bytes = await key_file.read()
        return _persist_certificate_record(
            domain=domain,
            cert_bytes=cert_bytes,
            key_bytes=key_bytes,
            auto_renew=auto_renew,
            current_user=current_user,
            db=db,
            request=request,
            audit_action="cert_upload" if not cert_id else "cert_update",
            success_message="证书上传成功" if not cert_id else "证书更新成功",
            cert_id=cert_id,
            cert_filename=cert_file.filename,
            key_filename=key_file.filename,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传证书失败: {str(e)}",
        )


@router.post("/parse-archive", summary="解析压缩包并提取域名（预览）")
async def parse_certificate_archive(
    archive_file: UploadFile = File(...), current_user: User = Depends(get_current_user)
):
    """解析压缩包，提取证书中的域名信息（不保存）"""
    if not archive_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请上传有效的压缩包文件"
        )

    try:
        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            archive_path = tmp_dir_path / (archive_file.filename or "archive")
            archive_bytes = await archive_file.read()
            archive_path.write_bytes(archive_bytes)

            extracted_dir = tmp_dir_path / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            _extract_archive(archive_path, extracted_dir)

            # 查找证书文件（不需要域名匹配，因为我们要从证书中提取域名）
            cert_candidates: List[Path] = []
            key_candidates: List[Path] = []

            for file in extracted_dir.rglob("*"):
                if not file.is_file():
                    continue
                suffix = file.suffix.lower()
                role = None
                if suffix in (CERT_EXTENSIONS - {".pem"}):
                    role = "cert"
                elif suffix in (KEY_EXTENSIONS - {".pem"}):
                    role = "key"
                elif suffix == ".pem":
                    role = _classify_pem_file(file)

                if role == "cert":
                    cert_candidates.append(file)
                elif role == "key":
                    key_candidates.append(file)

            if not cert_candidates:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="压缩包中未找到证书文件",
                )

            # 优先从文件名中提取域名
            domain = None
            cert_path = None

            # 首先尝试从文件名中提取域名
            for cert_file in cert_candidates:
                domain_from_filename = _extract_domain_from_filename(cert_file)
                if domain_from_filename:
                    domain = domain_from_filename
                    cert_path = cert_file
                    break

            # 如果文件名中没有找到域名，使用第一个证书文件并从证书内容中提取
            if not domain:
                cert_path = cert_candidates[0]
                cert_info = get_certificate_info(str(cert_path))
                domain = cert_info.get("domain")

            # 如果还是没找到，尝试从其他证书文件名中提取
            if not domain:
                for cert_file in cert_candidates:
                    domain_from_filename = _extract_domain_from_filename(cert_file)
                    if domain_from_filename:
                        domain = domain_from_filename
                        break

            if not domain:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="无法从证书文件名或内容中提取域名信息",
                )

            # 获取证书详细信息（用于显示颁发者、有效期等）
            if cert_path:
                cert_info = get_certificate_info(str(cert_path))
            else:
                cert_info = {}

            return {
                "success": True,
                "domain": domain,
                "issuer": cert_info.get("issuer"),
                "valid_from": cert_info.get("valid_from"),
                "valid_to": cert_info.get("valid_to"),
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析压缩包失败: {str(e)}",
        )


@router.post("/upload-archive", summary="上传压缩包并自动解析证书")
async def upload_certificate_archive(
    request: Request,
    domain: str = Form(None),
    archive_file: UploadFile = File(...),
    auto_renew: bool = Form(False),
    cert_id: Optional[int] = Form(None),  # 如果提供，则更新现有证书
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上传包含证书与私钥的压缩包"""
    if not archive_file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="请上传有效的压缩包文件"
        )

    try:
        with TemporaryDirectory() as tmp_dir:
            tmp_dir_path = Path(tmp_dir)
            archive_path = tmp_dir_path / (archive_file.filename or "archive")
            archive_bytes = await archive_file.read()
            archive_path.write_bytes(archive_bytes)

            extracted_dir = tmp_dir_path / "extracted"
            extracted_dir.mkdir(parents=True, exist_ok=True)
            _extract_archive(archive_path, extracted_dir)

            # 如果未提供域名，尝试从证书文件名或内容中提取
            if not domain:
                cert_candidates: List[Path] = []
                for file in extracted_dir.rglob("*"):
                    if not file.is_file():
                        continue
                    suffix = file.suffix.lower()
                    role = None
                    if suffix in (CERT_EXTENSIONS - {".pem"}):
                        role = "cert"
                    elif suffix == ".pem":
                        role = _classify_pem_file(file)
                    if role == "cert":
                        cert_candidates.append(file)

                if cert_candidates:
                    # 优先从文件名中提取域名
                    for cert_file in cert_candidates:
                        domain_from_filename = _extract_domain_from_filename(cert_file)
                        if domain_from_filename:
                            domain = domain_from_filename
                            break

                    # 如果文件名中没有找到，从证书内容中提取
                    if not domain:
                        cert_info = get_certificate_info(str(cert_candidates[0]))
                        domain = cert_info.get("domain")

                    if not domain:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="无法从证书文件名或内容中提取域名，请手动输入域名",
                        )

            if not domain:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请提供域名或确保压缩包中的证书包含域名信息",
                )

            cert_path, key_path = _discover_cert_and_key(extracted_dir, domain)

            if not cert_path or not key_path:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="压缩包中未找到有效的证书或私钥文件",
                )

            cert_bytes = cert_path.read_bytes()
            key_bytes = key_path.read_bytes()
            
            # 从解压后的文件路径中提取原始文件名
            cert_filename = cert_path.name
            key_filename = key_path.name

        return _persist_certificate_record(
            domain=domain,
            cert_bytes=cert_bytes,
            key_bytes=key_bytes,
            auto_renew=auto_renew,
            current_user=current_user,
            db=db,
            request=request,
            audit_action="cert_upload_archive" if not cert_id else "cert_update",
            success_message="证书压缩包上传成功" if not cert_id else "证书更新成功",
            cert_id=cert_id,
            cert_filename=cert_filename,
            key_filename=key_filename,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解析压缩包失败: {str(e)}",
        )


@router.post("/request", summary="通过 certbot 自动申请证书")
async def request_cert(
    request_data: CertificateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """通过 certbot 自动申请证书"""
    # 调用 certbot 申请证书
    result = request_certificate(
        domains=request_data.domains,
        email=request_data.email,
        validation_method=request_data.validation_method,
    )

    if not result["success"]:
        return {
            "success": False,
            "message": result["message"],
            "output": result["output"],
        }

    # 保存证书记录
    if result["cert_path"] and result["key_path"]:
        # 获取证书信息
        cert_info = get_certificate_info(result["cert_path"])

        # 解析有效期
        valid_from = None
        valid_to = None
        if cert_info.get("valid_from"):
            try:
                valid_from = datetime.fromisoformat(
                    cert_info["valid_from"].replace("Z", "+00:00")
                )
            except:
                pass
        if cert_info.get("valid_to"):
            try:
                valid_to = datetime.fromisoformat(
                    cert_info["valid_to"].replace("Z", "+00:00")
                )
            except:
                pass

        cert = Certificate(
            domain=request_data.domains[0],
            cert_path=result["cert_path"],
            key_path=result["key_path"],
            issuer=cert_info.get("issuer", "Let's Encrypt"),
            valid_from=valid_from,
            valid_to=valid_to,
            auto_renew=True,  # 自动申请的证书默认开启自动续期
            created_by_id=current_user.id,
        )
        db.add(cert)
        db.commit()
        db.refresh(cert)

        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="cert_request",
            target=request_data.domains[0],
            details={"domains": request_data.domains, "email": request_data.email},
            ip_address=get_client_ip(request),
        )

        return {
            "success": True,
            "message": "证书申请成功",
            "output": result["output"],
            "certificate": {
                "id": cert.id,
                "domain": cert.domain,
                "cert_path": cert.cert_path,
                "key_path": cert.key_path,
            },
        }

    return {"success": True, "message": result["message"], "output": result["output"]}


@router.post("/renew/{cert_id}", summary="手动续期证书")
async def renew_cert(
    cert_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动续期指定证书（对于手动上传的证书，会尝试通过certbot申请新证书）"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()

    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在")

    # 先尝试通过 certbot 续期（适用于通过certbot申请的证书）
    result = renew_certificate(domain=cert.domain)

    # 如果续期失败，可能是因为证书是手动上传的，certbot中没有记录
    # 这种情况下，我们可以尝试重新申请证书（如果用户配置了邮箱等信息）
    # 但目前先返回错误，提示用户手动更新证书
    if not result["success"]:
        # 检查是否是因为certbot中没有该域名的记录
        if "No such certificate" in result.get("output", "") or "certificate not found" in result.get("output", "").lower():
            return {
                "success": False,
                "message": f"该证书是通过手动上传的，无法自动续期。请通过重新上传功能手动更新证书，或通过申请证书功能使用certbot自动申请新证书。",
                "output": result.get("output", "")
            }

    # 如果续期成功，更新证书信息
    if result["success"]:
        # 如果续期成功，certbot会更新证书文件，我们需要更新数据库中的证书信息
        # 但手动上传的证书路径可能不在certbot的标准路径，需要重新读取证书文件
        cert_info = get_certificate_info(cert.cert_path)

        if cert_info.get("valid_to"):
            try:
                cert.valid_to = datetime.fromisoformat(
                    cert_info["valid_to"].replace("Z", "+00:00")
                )
            except:
                pass

        if cert_info.get("issuer"):
            cert.issuer = cert_info["issuer"]

        db.commit()

    # 记录操作日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="cert_renew",
        target=cert.domain,
        details={"success": result["success"]},
        ip_address=get_client_ip(request),
    )

    return result


@router.post("/renew-all", summary="续期所有证书")
async def renew_all_certs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """续期所有证书"""
    # 调用 certbot 续期所有证书
    result = renew_certificate(domain=None)

    # 更新所有证书的信息
    certificates = db.query(Certificate).all()
    for cert in certificates:
        cert_info = get_certificate_info(cert.cert_path)

        if cert_info.get("valid_to"):
            try:
                cert.valid_to = datetime.fromisoformat(
                    cert_info["valid_to"].replace("Z", "+00:00")
                )
            except:
                pass

    db.commit()

    # 记录操作日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="cert_renew_all",
        target="all",
        details={"success": result["success"]},
        ip_address=get_client_ip(request),
    )

    return result


@router.delete("/{cert_id}", summary="删除证书")
async def delete_certificate(
    cert_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除证书"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()

    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在")

    # 删除证书文件
    cert_path = Path(cert.cert_path)
    key_path = Path(cert.key_path)

    if cert_path.exists():
        try:
            cert_path.unlink()
        except Exception:
            pass

    if key_path.exists():
        try:
            key_path.unlink()
        except Exception:
            pass

    domain = cert.domain

    # 删除数据库记录
    db.delete(cert)
    db.commit()

    # 记录操作日志
    create_audit_log(
        db=db,
        user_id=current_user.id,
        username=current_user.username,
        action="cert_delete",
        target=domain,
        details={},
        ip_address=get_client_ip(request),
    )

    return {"success": True, "message": "证书已删除"}


@router.put("/{cert_id}", summary="更新证书信息")
async def update_certificate(
    cert_id: int,
    request_data: CertificateUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新证书信息（如启用/禁用自动续期）"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()

    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="证书不存在")

    if request_data.auto_renew is not None:
        cert.auto_renew = request_data.auto_renew

    db.commit()

    return {"success": True, "message": "证书信息已更新"}


@router.get("/check-expiry", summary="检查证书过期时间")
async def check_certificate_expiry(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """检查所有证书的过期时间"""
    certificates = db.query(Certificate).all()

    result = []
    for cert in certificates:
        days_until_expiry = None
        if cert.valid_to:
            days_until_expiry = (cert.valid_to - datetime.now()).days

        result.append(
            {
                "id": cert.id,
                "domain": cert.domain,
                "valid_to": cert.valid_to.isoformat() if cert.valid_to else None,
                "days_until_expiry": days_until_expiry,
                "is_expiring_soon": days_until_expiry is not None
                and days_until_expiry <= 30,
            }
        )

    return {"success": True, "certificates": result}
