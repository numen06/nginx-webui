"""
Git 仓库同步工具
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.models import GitRepository
from app.utils.nginx import get_config_path


class GitSyncError(Exception):
    """Git 同步异常"""


def get_project_root() -> Path:
    """获取系统根目录"""
    return Path(__file__).resolve().parents[3]


def get_default_project_name() -> str:
    """获取默认项目名称（使用系统根目录名）"""
    return get_project_root().name


def get_workspace_dir(project_name: Optional[str] = None) -> Path:
    """获取本地 Git 工作目录"""
    data_root = Path(os.getenv("DATA_ROOT", "/app/data"))
    workspace = data_root / "git" / (project_name or get_default_project_name())
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _build_authenticated_url(
    repo_url: str,
    username: Optional[str],
    password: Optional[str],
) -> str:
    """构建带账号密码的仓库地址"""
    if not username or not password:
        return repo_url

    parsed = urllib.parse.urlsplit(repo_url)
    netloc = parsed.netloc
    if "@" in netloc:
        netloc = netloc.split("@", 1)[1]

    auth = f"{urllib.parse.quote(username, safe='')}:{urllib.parse.quote(password, safe='')}"
    netloc = f"{auth}@{netloc}"

    return urllib.parse.urlunsplit(
        (parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment)
    )


def _run_git(
    args: List[str],
    cwd: Optional[Path] = None,
) -> str:
    """运行 git 命令"""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        error_msg = result.stderr.strip() or result.stdout.strip() or "未知错误"
        raise GitSyncError(f"git {' '.join(args)} 失败: {error_msg}")
    return result.stdout.strip()


@contextmanager
def _temporary_auth_remote(workspace: Path, repo: GitRepository):
    """
    临时为 origin 设置带认证信息的地址，确保不会长久保存账号密码
    """
    if not (repo.username and repo.password):
        yield
        return

    auth_url = _build_authenticated_url(repo.repo_url, repo.username, repo.password)
    _run_git(["remote", "set-url", "origin", auth_url], cwd=workspace)
    try:
        yield
    finally:
        _run_git(["remote", "set-url", "origin", repo.repo_url], cwd=workspace)


def _ensure_repo(repo: GitRepository, workspace: Path) -> str:
    """确保本地仓库可用，必要时执行 clone"""
    branch = repo.branch or "main"
    git_dir = workspace / ".git"

    if not git_dir.exists():
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        auth_url = _build_authenticated_url(repo.repo_url, repo.username, repo.password)
        _run_git(["clone", "--branch", branch, auth_url, str(workspace)])
        if repo.username and repo.password:
            _run_git(["remote", "set-url", "origin", repo.repo_url], cwd=workspace)
        return "cloned"

    with _temporary_auth_remote(workspace, repo):
        _run_git(["fetch", "origin"], cwd=workspace)
        _run_git(["checkout", branch], cwd=workspace)
        _run_git(["pull", "--rebase", "origin", branch], cwd=workspace)
    return "updated"


def _export_nginx_config(workspace: Path, project_name: str) -> Dict[str, Any]:
    """将当前 Nginx 配置导出到仓库目录"""
    project_dir = workspace / project_name
    project_dir.mkdir(parents=True, exist_ok=True)

    config_path = get_config_path()
    if not config_path.exists():
        raise GitSyncError(f"未找到 Nginx 配置文件：{config_path}")

    target_path = project_dir / "nginx.conf"
    shutil.copy2(config_path, target_path)

    metadata = {
        "project_name": project_name,
        "source_config": str(config_path),
        "synced_at": datetime.now().isoformat(),
    }
    metadata_path = project_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8")

    return {
        "project_dir": str(project_dir),
        "config_file": str(target_path),
        "metadata_file": str(metadata_path),
    }


def sync_repository(repo: GitRepository) -> Dict[str, Any]:
    """同步当前配置到 Git 仓库"""
    project_name = repo.project_name or get_default_project_name()
    workspace = get_workspace_dir(project_name)
    action = _ensure_repo(repo, workspace)

    export_info = _export_nginx_config(workspace, project_name)

    _run_git(["add", "."], cwd=workspace)
    status = _run_git(["status", "--porcelain"], cwd=workspace)
    if not status.strip():
        return {
            "changed": False,
            "action": action,
            **export_info,
            "message": "没有需要提交的变更",
        }

    commit_message = f"sync nginx config {datetime.now().isoformat()}"
    _run_git(["config", "user.name", "nginx-webui"], cwd=workspace)
    _run_git(["config", "user.email", "nginx-webui@example.local"], cwd=workspace)
    _run_git(["commit", "-m", commit_message], cwd=workspace)

    with _temporary_auth_remote(workspace, repo):
        _run_git(["push", "origin", repo.branch or "main"], cwd=workspace)

    return {
        "changed": True,
        "action": action,
        **export_info,
        "message": "配置已同步至 Git 仓库",
        "commit_message": commit_message,
    }

