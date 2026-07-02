"""动态服务注册 API。"""

import base64
import binascii
import ipaddress
import socket
import time
from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import authenticate_user, get_current_user, get_user_by_token, User
from app.config import get_config
from app.database import SessionLocal, get_db
from app.models import DynamicService, DynamicServiceInstance
from app.utils.audit import create_audit_log, get_client_ip
from app.utils.dynamic_registry import (
    apply_dynamic_registry,
    dynamic_service_hosts,
    get_dynamic_config_preview,
    normalize_instance_id,
    normalize_route_prefix,
    normalize_service_name,
    normalize_target_url,
    validate_route_prefix_available,
)

try:
    import psutil
except ImportError:
    psutil = None


router = APIRouter(prefix="/api/dynamic-services", tags=["dynamic-services"])


class RegistryInstanceRequest(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    route_prefix: Optional[str] = Field(default=None, min_length=1, max_length=255)
    instance_id: str = Field(..., min_length=1, max_length=150)
    target_url: str = Field(..., min_length=1, max_length=500)
    ttl_seconds: Optional[int] = Field(default=None, ge=30, le=86400)
    description: Optional[str] = None


class RegistryInstanceRef(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    instance_id: str = Field(..., min_length=1, max_length=150)


class ServiceCreateRequest(BaseModel):
    service_name: str = Field(..., min_length=1, max_length=100)
    route_prefix: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: bool = True


class ServiceUpdateRequest(BaseModel):
    route_prefix: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    enabled: bool = True


class EnableRequest(BaseModel):
    enabled: bool


def _parse_configured_whitelist() -> Optional[List[ipaddress._BaseNetwork]]:
    whitelist = get_config().dynamic_registry.ip_whitelist
    if whitelist is None or not str(whitelist).strip():
        return None

    networks = []
    for item in str(whitelist).split(","):
        value = item.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"动态注册 IP 白名单配置无效: {value}",
            ) from exc
    return networks


def _auto_same_subnet_networks() -> List[ipaddress._BaseNetwork]:
    networks: List[ipaddress._BaseNetwork] = [
        ipaddress.ip_network("127.0.0.0/8"),
        ipaddress.ip_network("::1/128"),
    ]

    if psutil:
        for addresses in psutil.net_if_addrs().values():
            for address in addresses:
                if address.family not in (socket.AF_INET, socket.AF_INET6):
                    continue
                if not address.address or not address.netmask:
                    continue
                try:
                    iface = ipaddress.ip_interface(f"{address.address}/{address.netmask}")
                    networks.append(iface.network)
                except ValueError:
                    continue

    unique = []
    seen = set()
    for network in networks:
        key = str(network)
        if key not in seen:
            seen.add(key)
            unique.append(network)
    return unique


def _client_ip(request: Request) -> ipaddress._BaseAddress:
    raw_ip = request.client.host if request.client else ""
    try:
        return ipaddress.ip_address(raw_ip)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法识别客户端 IP: {raw_ip}",
        ) from exc


def _registry_auth(request: Request, db: Session) -> dict:
    client_ip = _client_ip(request)
    configured_whitelist = _parse_configured_whitelist()
    if configured_whitelist is not None:
        if any(client_ip in network for network in configured_whitelist):
            return {"method": "ip_whitelist", "user": None}
    else:
        if any(client_ip in network for network in _auto_same_subnet_networks()):
            return {"method": "auto_same_subnet", "user": None}

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        user = get_user_by_token(token.strip(), db)
        if user:
            return {"method": "auth_token", "user": user}

    if scheme.lower() == "basic" and token:
        try:
            decoded = base64.b64decode(token.strip()).decode("utf-8")
            username, separator, password = decoded.partition(":")
        except (binascii.Error, UnicodeDecodeError):
            username, separator, password = "", "", ""
        if separator:
            user = authenticate_user(db, username, password)
            if user:
                return {"method": "basic_auth", "user": user}

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="来源 IP 不在动态注册白名单内，且未提供有效的登录 Token 或 Basic 认证",
    )


def _serialize_instance(instance: DynamicServiceInstance) -> dict:
    now = datetime.now()
    expires_at = instance.last_heartbeat_at + timedelta(seconds=instance.ttl_seconds)
    return {
        "id": instance.id,
        "instance_id": instance.instance_id,
        "target_url": instance.target_url,
        "status": instance.status,
        "last_heartbeat_at": instance.last_heartbeat_at.isoformat() if instance.last_heartbeat_at else None,
        "ttl_seconds": instance.ttl_seconds,
        "expires_at": expires_at.isoformat(),
        "expired": expires_at <= now,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
    }


def _serialize_service(service: DynamicService, include_instances: bool = True) -> dict:
    instances = service.instances if include_instances else []
    active_count = 0
    now = datetime.now()
    for instance in instances:
        if instance.status == "active" and instance.last_heartbeat_at + timedelta(seconds=instance.ttl_seconds) > now:
            active_count += 1
    return {
        "id": service.id,
        "service_name": service.service_name,
        "route_prefix": service.route_prefix,
        "virtual_hosts": dynamic_service_hosts(service.service_name),
        "enabled": service.enabled,
        "description": service.description,
        "active_instance_count": active_count,
        "instance_count": len(instances),
        "created_at": service.created_at.isoformat() if service.created_at else None,
        "updated_at": service.updated_at.isoformat() if service.updated_at else None,
        "instances": [_serialize_instance(instance) for instance in instances],
    }


def _apply_or_raise(db: Session) -> dict:
    result = apply_dynamic_registry(db)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result)
    return result


def _audit_registry(
    db: Session,
    request: Request,
    action: str,
    service_name: str,
    auth_info: dict,
    details: Optional[dict] = None,
) -> None:
    auth_user = auth_info.get("user")
    payload = details.copy() if details else {}
    payload["auth_method"] = auth_info.get("method")
    create_audit_log(
        db=db,
        user_id=auth_user.id if auth_user else None,
        username=auth_user.username if auth_user else f"registry:{service_name}",
        action=action,
        target=service_name,
        details=payload,
        ip_address=get_client_ip(request),
    )


@router.get("", summary="动态服务列表")
async def list_dynamic_services(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    services = db.query(DynamicService).order_by(DynamicService.service_name.asc()).all()
    return {"success": True, "services": [_serialize_service(service) for service in services]}


@router.get("/auth-status", summary="动态注册鉴权状态")
async def get_registry_auth_status(current_user: User = Depends(get_current_user)):
    configured = _parse_configured_whitelist()
    auto_networks = [] if configured is not None else _auto_same_subnet_networks()
    return {
        "success": True,
        "auth_token_enabled": True,
        "basic_auth_enabled": True,
        "explicit_ip_whitelist_enabled": configured is not None,
        "ip_whitelist": [str(network) for network in configured] if configured is not None else [],
        "auto_same_subnet_enabled": configured is None,
        "auto_same_subnet_networks": [str(network) for network in auto_networks],
        "domain_suffix": get_config().dynamic_registry.domain_suffix,
        "default_ttl_seconds": get_config().dynamic_registry.default_ttl_seconds,
        "cleanup_interval_seconds": get_config().dynamic_registry.cleanup_interval_seconds,
    }


@router.get("/generated-config", summary="动态服务生成配置预览")
async def get_generated_dynamic_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {"success": True, "content": get_dynamic_config_preview(db)}


@router.post("", summary="创建动态服务")
async def create_dynamic_service(
    payload: ServiceCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        service_name = normalize_service_name(payload.service_name)
        route_prefix = normalize_route_prefix(payload.route_prefix)
        validate_route_prefix_available(db, route_prefix)
        if db.query(DynamicService).filter(DynamicService.service_name == service_name).first():
            raise ValueError(f"服务名已存在: {service_name}")

        service = DynamicService(
            service_name=service_name,
            route_prefix=route_prefix,
            enabled=payload.enabled,
            description=payload.description,
        )
        db.add(service)
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        db.refresh(service)
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dynamic_service_create",
            target=service.service_name,
            details={"route_prefix": service.route_prefix, "enabled": service.enabled},
            ip_address=get_client_ip(request),
        )
        return {"success": True, "service": _serialize_service(service), "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.put("/service/{service_id}", summary="更新动态服务")
async def update_dynamic_service(
    service_id: int,
    payload: ServiceUpdateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.query(DynamicService).filter(DynamicService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")
    try:
        route_prefix = normalize_route_prefix(payload.route_prefix)
        validate_route_prefix_available(db, route_prefix, service_id=service.id)
        service.route_prefix = route_prefix
        service.description = payload.description
        service.enabled = payload.enabled
        service.updated_at = datetime.now()
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        db.refresh(service)
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dynamic_service_update",
            target=service.service_name,
            details={"route_prefix": service.route_prefix, "enabled": service.enabled},
            ip_address=get_client_ip(request),
        )
        return {"success": True, "service": _serialize_service(service), "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/service/{service_id}/enable", summary="启停动态服务")
async def enable_dynamic_service(
    service_id: int,
    payload: EnableRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.query(DynamicService).filter(DynamicService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")
    try:
        service.enabled = payload.enabled
        service.updated_at = datetime.now()
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        db.refresh(service)
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dynamic_service_enable",
            target=service.service_name,
            details={"enabled": service.enabled},
            ip_address=get_client_ip(request),
        )
        return {"success": True, "service": _serialize_service(service), "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise


@router.delete("/service/{service_id}", summary="删除动态服务")
async def delete_dynamic_service(
    service_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.query(DynamicService).filter(DynamicService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")
    service_name = service.service_name
    try:
        db.delete(service)
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dynamic_service_delete",
            target=service_name,
            details={},
            ip_address=get_client_ip(request),
        )
        return {"success": True, "message": "服务已删除", "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise


@router.post("/service/{service_id}/instances/{instance_id}/offline", summary="强制下线实例")
async def offline_dynamic_instance(
    service_id: int,
    instance_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = db.query(DynamicService).filter(DynamicService.id == service_id).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")
    instance = (
        db.query(DynamicServiceInstance)
        .filter(DynamicServiceInstance.service_id == service.id)
        .filter(DynamicServiceInstance.instance_id == instance_id)
        .first()
    )
    if not instance:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实例不存在")
    try:
        instance.status = "offline"
        instance.updated_at = datetime.now()
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        create_audit_log(
            db=db,
            user_id=current_user.id,
            username=current_user.username,
            action="dynamic_instance_offline",
            target=f"{service.service_name}/{instance_id}",
            details={},
            ip_address=get_client_ip(request),
        )
        return {"success": True, "message": "实例已下线", "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise


@router.post("/register", summary="注册或更新动态服务实例")
async def register_dynamic_instance(
    payload: RegistryInstanceRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_info = _registry_auth(request, db)
    try:
        service_name = normalize_service_name(payload.service_name)
        route_prefix = normalize_route_prefix(payload.route_prefix or service_name)
        instance_id = normalize_instance_id(payload.instance_id)
        target_url = normalize_target_url(payload.target_url)
        ttl_seconds = payload.ttl_seconds or get_config().dynamic_registry.default_ttl_seconds

        service = db.query(DynamicService).filter(DynamicService.service_name == service_name).first()
        if service is None:
            validate_route_prefix_available(db, route_prefix)
            service = DynamicService(
                service_name=service_name,
                route_prefix=route_prefix,
                enabled=True,
                description=payload.description,
            )
            db.add(service)
            db.flush()
        else:
            if service.route_prefix != route_prefix:
                validate_route_prefix_available(db, route_prefix, service_id=service.id)
                service.route_prefix = route_prefix
            if payload.description is not None:
                service.description = payload.description
            service.enabled = True
            service.updated_at = datetime.now()

        instance = (
            db.query(DynamicServiceInstance)
            .filter(DynamicServiceInstance.service_id == service.id)
            .filter(DynamicServiceInstance.instance_id == instance_id)
            .first()
        )
        now = datetime.now()
        if instance is None:
            instance = DynamicServiceInstance(
                service_id=service.id,
                instance_id=instance_id,
                target_url=target_url,
                status="active",
                last_heartbeat_at=now,
                ttl_seconds=ttl_seconds,
            )
            db.add(instance)
        else:
            instance.target_url = target_url
            instance.status = "active"
            instance.last_heartbeat_at = now
            instance.ttl_seconds = ttl_seconds
            instance.updated_at = now

        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        db.refresh(service)
        _audit_registry(
            db,
            request,
            "dynamic_instance_register",
            service_name,
            auth_info,
            {"instance_id": instance_id, "route_prefix": route_prefix, "target_url": target_url},
        )
        return {"success": True, "message": "实例已注册并生效", "service": _serialize_service(service), "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/heartbeat", summary="动态服务实例心跳")
async def heartbeat_dynamic_instance(
    payload: RegistryInstanceRef,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_info = _registry_auth(request, db)
    service_name = normalize_service_name(payload.service_name)
    instance_id = normalize_instance_id(payload.instance_id)
    service = db.query(DynamicService).filter(DynamicService.service_name == service_name).first()
    if not service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="服务不存在")
    instance = (
        db.query(DynamicServiceInstance)
        .filter(DynamicServiceInstance.service_id == service.id)
        .filter(DynamicServiceInstance.instance_id == instance_id)
        .first()
    )
    if not instance or instance.status != "active":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="实例不存在或未上线")
    now = datetime.now()
    instance.last_heartbeat_at = now
    instance.updated_at = now
    db.commit()
    _audit_registry(
        db,
        request,
        "dynamic_instance_heartbeat",
        service_name,
        auth_info,
        {"instance_id": instance_id},
    )
    return {"success": True, "message": "心跳已更新", "instance": _serialize_instance(instance)}


@router.post("/unregister", summary="下线动态服务实例")
async def unregister_dynamic_instance(
    payload: RegistryInstanceRef,
    request: Request,
    db: Session = Depends(get_db),
):
    auth_info = _registry_auth(request, db)
    service_name = normalize_service_name(payload.service_name)
    instance_id = normalize_instance_id(payload.instance_id)
    service = db.query(DynamicService).filter(DynamicService.service_name == service_name).first()
    if not service:
        return {"success": True, "message": "服务不存在，视为已下线"}
    instance = (
        db.query(DynamicServiceInstance)
        .filter(DynamicServiceInstance.service_id == service.id)
        .filter(DynamicServiceInstance.instance_id == instance_id)
        .first()
    )
    if not instance:
        return {"success": True, "message": "实例不存在，视为已下线"}
    try:
        instance.status = "offline"
        instance.updated_at = datetime.now()
        db.flush()
        apply_result = _apply_or_raise(db)
        db.commit()
        _audit_registry(
            db,
            request,
            "dynamic_instance_unregister",
            service_name,
            auth_info,
            {"instance_id": instance_id},
        )
        return {"success": True, "message": "实例已下线", "apply_result": apply_result}
    except HTTPException:
        db.rollback()
        raise


def expire_dynamic_instances_once() -> dict:
    db = SessionLocal()
    try:
        now = datetime.now()
        expired = []
        instances = (
            db.query(DynamicServiceInstance)
            .filter(DynamicServiceInstance.status == "active")
            .all()
        )
        for instance in instances:
            expires_at = instance.last_heartbeat_at + timedelta(seconds=instance.ttl_seconds)
            if expires_at <= now:
                instance.status = "expired"
                instance.updated_at = now
                expired.append(instance)

        if not expired:
            return {"success": True, "expired": 0, "reloaded": False}

        db.flush()
        result = apply_dynamic_registry(db)
        if not result.get("success"):
            db.rollback()
            return {"success": False, "expired": len(expired), "apply_result": result}

        db.commit()
        return {"success": True, "expired": len(expired), "reloaded": True, "apply_result": result}
    finally:
        db.close()


def start_dynamic_registry_cleanup_scheduler() -> None:
    import threading

    def _worker():
        while True:
            interval = max(10, get_config().dynamic_registry.cleanup_interval_seconds)
            time.sleep(interval)
            try:
                expire_dynamic_instances_once()
            except Exception as exc:
                import logging

                logging.warning("动态服务过期实例清理失败: %s", exc)

    threading.Thread(target=_worker, daemon=True).start()
