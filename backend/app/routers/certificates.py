"""
证书管理路由
"""
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.auth import get_current_user, User
from app.config import get_config
from app.models import Certificate
from app.utils.certbot import (
    request_certificate, renew_certificate, list_certificates, get_certificate_info
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


@router.get("", summary="获取证书列表")
async def get_certificates(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取所有证书列表"""
    certificates = db.query(Certificate).order_by(Certificate.created_at.desc()).all()
    
    result = []
    for cert in certificates:
        # 检查证书是否即将过期（30天内）
        days_until_expiry = None
        if cert.valid_to:
            days_until_expiry = (cert.valid_to - datetime.utcnow()).days
        
        result.append({
            "id": cert.id,
            "domain": cert.domain,
            "cert_path": cert.cert_path,
            "key_path": cert.key_path,
            "issuer": cert.issuer,
            "valid_from": cert.valid_from.isoformat() if cert.valid_from else None,
            "valid_to": cert.valid_to.isoformat() if cert.valid_to else None,
            "auto_renew": cert.auto_renew,
            "days_until_expiry": days_until_expiry,
            "created_at": cert.created_at.isoformat() if cert.created_at else None
        })
    
    return {
        "success": True,
        "certificates": result
    }


@router.get("/{cert_id}", summary="获取证书详情")
async def get_certificate(
    cert_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取证书详情"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="证书不存在"
        )
    
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
            "valid_from": cert.valid_from.isoformat() if cert.valid_from else cert_info.get("valid_from"),
            "valid_to": cert.valid_to.isoformat() if cert.valid_to else cert_info.get("valid_to"),
            "auto_renew": cert.auto_renew,
            "created_at": cert.created_at.isoformat() if cert.created_at else None
        }
    }


@router.post("/upload", summary="手动上传证书")
async def upload_certificate(
    request: Request,
    domain: str = Form(...),
    cert_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    auto_renew: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """手动上传证书"""
    config = get_config()
    ssl_dir = Path(config.nginx.ssl_dir)
    ssl_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存证书文件
    cert_path = ssl_dir / f"{domain}.crt"
    key_path = ssl_dir / f"{domain}.key"
    
    try:
        # 保存证书文件
        with open(cert_path, 'wb') as f:
            content = await cert_file.read()
            f.write(content)
        
        # 保存私钥文件
        with open(key_path, 'wb') as f:
            content = await key_file.read()
            f.write(content)
        
        # 获取证书信息
        cert_info = get_certificate_info(str(cert_path))
        
        # 解析有效期
        valid_from = None
        valid_to = None
        if cert_info.get("valid_from"):
            try:
                valid_from = datetime.fromisoformat(cert_info["valid_from"].replace('Z', '+00:00'))
            except:
                pass
        if cert_info.get("valid_to"):
            try:
                valid_to = datetime.fromisoformat(cert_info["valid_to"].replace('Z', '+00:00'))
            except:
                pass
        
        # 创建证书记录
        cert = Certificate(
            domain=domain,
            cert_path=str(cert_path),
            key_path=str(key_path),
            issuer=cert_info.get("issuer"),
            valid_from=valid_from,
            valid_to=valid_to,
            auto_renew=auto_renew,
            created_by_id=current_user.id
        )
        db.add(cert)
        db.commit()
        db.refresh(cert)
        
        # 记录操作日志
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="cert_upload",
            target=domain,
            details={"cert_path": str(cert_path), "key_path": str(key_path)},
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "证书上传成功",
            "certificate": {
                "id": cert.id,
                "domain": cert.domain,
                "cert_path": cert.cert_path,
                "key_path": cert.key_path
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传证书失败: {str(e)}"
        )


@router.post("/request", summary="通过 certbot 自动申请证书")
async def request_cert(
    request_data: CertificateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """通过 certbot 自动申请证书"""
    # 调用 certbot 申请证书
    result = request_certificate(
        domains=request_data.domains,
        email=request_data.email,
        validation_method=request_data.validation_method
    )
    
    if not result["success"]:
        return {
            "success": False,
            "message": result["message"],
            "output": result["output"]
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
                valid_from = datetime.fromisoformat(cert_info["valid_from"].replace('Z', '+00:00'))
            except:
                pass
        if cert_info.get("valid_to"):
            try:
                valid_to = datetime.fromisoformat(cert_info["valid_to"].replace('Z', '+00:00'))
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
            created_by_id=current_user.id
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
            ip_address=get_client_ip(request)
        )
        
        return {
            "success": True,
            "message": "证书申请成功",
            "output": result["output"],
            "certificate": {
                "id": cert.id,
                "domain": cert.domain,
                "cert_path": cert.cert_path,
                "key_path": cert.key_path
            }
        }
    
    return {
        "success": True,
        "message": result["message"],
        "output": result["output"]
    }


@router.post("/renew/{cert_id}", summary="手动续期证书")
async def renew_cert(
    cert_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """手动续期指定证书"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="证书不存在"
        )
    
    # 调用 certbot 续期
    result = renew_certificate(domain=cert.domain)
    
    # 如果续期成功，更新证书信息
    if result["success"]:
        cert_info = get_certificate_info(cert.cert_path)
        
        if cert_info.get("valid_to"):
            try:
                cert.valid_to = datetime.fromisoformat(cert_info["valid_to"].replace('Z', '+00:00'))
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
        ip_address=get_client_ip(request)
    )
    
    return result


@router.post("/renew-all", summary="续期所有证书")
async def renew_all_certs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
                cert.valid_to = datetime.fromisoformat(cert_info["valid_to"].replace('Z', '+00:00'))
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
        ip_address=get_client_ip(request)
    )
    
    return result


@router.delete("/{cert_id}", summary="删除证书")
async def delete_certificate(
    cert_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除证书"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="证书不存在"
        )
    
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
        ip_address=get_client_ip(request)
    )
    
    return {
        "success": True,
        "message": "证书已删除"
    }


@router.put("/{cert_id}", summary="更新证书信息")
async def update_certificate(
    cert_id: int,
    request_data: CertificateUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新证书信息（如启用/禁用自动续期）"""
    cert = db.query(Certificate).filter(Certificate.id == cert_id).first()
    
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="证书不存在"
        )
    
    if request_data.auto_renew is not None:
        cert.auto_renew = request_data.auto_renew
    
    db.commit()
    
    return {
        "success": True,
        "message": "证书信息已更新"
    }


@router.get("/check-expiry", summary="检查证书过期时间")
async def check_certificate_expiry(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """检查所有证书的过期时间"""
    certificates = db.query(Certificate).all()
    
    result = []
    for cert in certificates:
        days_until_expiry = None
        if cert.valid_to:
            days_until_expiry = (cert.valid_to - datetime.utcnow()).days
        
        result.append({
            "id": cert.id,
            "domain": cert.domain,
            "valid_to": cert.valid_to.isoformat() if cert.valid_to else None,
            "days_until_expiry": days_until_expiry,
            "is_expiring_soon": days_until_expiry is not None and days_until_expiry <= 30
        })
    
    return {
        "success": True,
        "certificates": result
    }

