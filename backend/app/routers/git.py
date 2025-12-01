"""
Git 仓库配置路由
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import User, get_current_user
from app.database import get_db
from app.models import GitRepository
from app.utils.git_sync import (
    GitSyncError,
    get_default_project_name,
    sync_repository,
)

router = APIRouter(prefix="/api/git", tags=["git"])


class GitConfigRequest(BaseModel):
    """Git 配置请求"""

    repo_url: str = Field(..., description="Git 仓库地址")
    username: Optional[str] = Field(None, description="Git 账号")
    password: Optional[str] = Field(None, description="Git 密码（留空表示不变）")
    branch: str = Field(default="main", description="目标分支")
    project_name: Optional[str] = Field(None, description="项目名称（用于区分 git 目录）")


def _serialize_repo(repo: Optional[GitRepository]) -> Optional[dict]:
    if repo is None:
        return None
    return {
        "project_name": repo.project_name,
        "repo_url": repo.repo_url,
        "username": repo.username,
        "branch": repo.branch,
        "has_password": bool(repo.password),
        "last_synced_at": repo.last_synced_at.isoformat() if repo.last_synced_at else None
        if repo.last_synced_at
        else None,
        "last_sync_status": repo.last_sync_status,
        "last_sync_message": repo.last_sync_message,
    }


def _get_repo(db: Session) -> Optional[GitRepository]:
    return db.query(GitRepository).order_by(GitRepository.id.asc()).first()


@router.get("/config", summary="获取 Git 配置")
async def get_git_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = _get_repo(db)
    project_name = repo.project_name if repo else None
    return {
        "success": True,
        "project_name": project_name,
        "default_project_name": get_default_project_name(),
        "config": _serialize_repo(repo),
    }


@router.post("/config", summary="保存 Git 配置")
async def save_git_config(
    request_data: GitConfigRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project_name = (request_data.project_name or "").strip()
    if not project_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="项目名称不能为空",
        )

    repo = _get_repo(db)

    now = datetime.now()
    if repo is None:
        repo = GitRepository(
            project_name=project_name,
            repo_url=request_data.repo_url.strip(),
            username=request_data.username.strip() if request_data.username else None,
            password=request_data.password if request_data.password else None,
            branch=request_data.branch or "main",
            created_at=now,
            updated_at=now,
        )
        db.add(repo)
    else:
        repo.project_name = project_name
        repo.repo_url = request_data.repo_url.strip()
        repo.username = request_data.username.strip() if request_data.username else None
        if request_data.password is not None:
            repo.password = request_data.password if request_data.password else None
        repo.branch = request_data.branch or repo.branch or "main"
        repo.updated_at = now

    db.commit()
    db.refresh(repo)

    return {
        "success": True,
        "message": "Git 配置已保存",
        "project_name": project_name,
        "config": _serialize_repo(repo),
    }


@router.post("/sync", summary="同步配置到 Git 仓库")
async def sync_git_repository(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = _get_repo(db)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="尚未配置 Git 仓库",
        )
    if not repo.project_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先设置项目名称",
        )

    if not repo.username or not repo.password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先配置 Git 账号和密码",
        )

    try:
        result = sync_repository(repo)
        repo.last_synced_at = datetime.now()
        repo.last_sync_status = "success" if result.get("changed") else "skipped"
        repo.last_sync_message = result.get("message")
        db.commit()
    except GitSyncError as exc:
        repo.last_synced_at = datetime.now()
        repo.last_sync_status = "failed"
        repo.last_sync_message = str(exc)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    return {
        "success": True,
        "project_name": repo.project_name,
        "result": result,
    }

