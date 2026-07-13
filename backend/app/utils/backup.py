"""
配置备份工具
"""

import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.config import get_config
from app.models import ConfigBackup
from app.utils.nginx import (
    get_config_path,
    get_config_dir,
    get_working_config_dir,
    get_working_config_path,
    _should_skip_config_item,
)


def create_backup(
    db: Session,
    created_by_id: Optional[int] = None,
    is_last_version: bool = False,
    source_path: Optional[Path] = None,
) -> ConfigBackup:
    """
    创建配置目录备份（始终备份当前实际生效的线上 conf/）

    Args:
        db: 数据库会话
        created_by_id: 创建者用户ID
        is_last_version: 是否标记为最后版本
        source_path: 可选的源文件路径，如果提供则备份该文件，否则备份当前线上配置

    Returns:
        ConfigBackup: 备份记录
    """
    # 备份当前实际使用的 Nginx 配置目录，而不是固定的 config.yaml 路径。
    config = get_config()
    if source_path is None:
        config_path = get_config_dir()
    else:
        config_path = source_path
    backup_dir = Path(config.backup.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"nginx-conf.backup.{timestamp}.zip"
    backup_path = backup_dir / backup_filename

    # 压缩配置目录；如果传入旧式单文件路径，则兼容压缩为 nginx.conf。
    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as archive:
        if config_path.is_dir():
            for item in sorted(config_path.rglob("*")):
                if item.is_file() and not _should_skip_config_item(item):
                    archive.write(item, item.relative_to(config_path))
        else:
            archive.write(config_path, "nginx.conf")

    # 如果标记为最后版本，先取消其他备份的最后版本标记
    if is_last_version:
        db.query(ConfigBackup).filter(ConfigBackup.is_last_version == True).update(
            {"is_last_version": False}
        )

    # 创建备份记录
    backup_record = ConfigBackup(
        filename=backup_filename,
        file_path=str(backup_path),
        created_by_id=created_by_id,
        created_at=datetime.now(),
        is_last_version=is_last_version,
    )
    db.add(backup_record)
    db.commit()
    db.refresh(backup_record)

    # 清理旧备份
    cleanup_old_backups(db)

    return backup_record


def list_backups(db: Session, limit: Optional[int] = None) -> List[ConfigBackup]:
    """
    列出所有备份，并确保记录与实际文件保持一致。

    Args:
        db: 数据库会话
        limit: 限制返回数量

    Returns:
        List[ConfigBackup]: 备份列表
    """
    records = db.query(ConfigBackup).order_by(ConfigBackup.created_at.desc()).all()
    valid_backups: List[ConfigBackup] = []
    removed = False

    for backup in records:
        backup_path = Path(backup.file_path)
        if backup_path.exists():
            valid_backups.append(backup)
            continue
        # 备份文件已丢失，删除数据表中的孤儿记录
        db.delete(backup)
        removed = True

    if removed:
        db.commit()

    if limit is not None:
        return valid_backups[:limit]
    return valid_backups


def get_backup(db: Session, backup_id: int) -> Optional[ConfigBackup]:
    """获取指定备份"""
    return db.query(ConfigBackup).filter(ConfigBackup.id == backup_id).first()


def set_last_version(db: Session, backup_id: int) -> bool:
    """
    设置指定备份为最后版本，并取消其他备份的最后版本标记

    Args:
        db: 数据库会话
        backup_id: 备份ID

    Returns:
        bool: 是否成功
    """
    backup = get_backup(db, backup_id)
    if not backup:
        return False

    # 取消所有备份的最后版本标记
    db.query(ConfigBackup).filter(ConfigBackup.is_last_version == True).update(
        {"is_last_version": False}
    )

    # 设置指定备份为最后版本
    backup.is_last_version = True
    db.commit()

    return True


def restore_backup(db: Session, backup_id: int) -> bool:
    """
    恢复指定备份

    Args:
        db: 数据库会话
        backup_id: 备份ID

    Returns:
        bool: 是否成功
    """
    backup = get_backup(db, backup_id)
    if not backup:
        return False

    backup_path = Path(backup.file_path)
    if not backup_path.exists():
        # 文件缺失时删除这条记录，避免列表中出现无效项
        db.delete(backup)
        db.commit()
        return False

    # 回滚到「临时配置/工作副本」，而不直接修改实际运行的 conf/。
    if zipfile.is_zipfile(backup_path):
        working_dir = get_working_config_dir()
        if working_dir.exists():
            shutil.rmtree(working_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(backup_path, "r") as archive:
            for member in archive.infolist():
                target = (working_dir / member.filename).resolve()
                try:
                    target.relative_to(working_dir.resolve())
                except ValueError:
                    continue
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, open(target, "wb") as dest:
                    shutil.copyfileobj(source, dest)
    else:
        # 兼容旧单文件备份：只恢复到工作副本 nginx.conf。
        working_path = get_working_config_path()
        working_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_path, working_path)

    return True


def cleanup_old_backups(db: Session):
    """
    清理旧备份，只保留最近 N 个

    Args:
        db: 数据库会话
    """
    config = get_config()
    max_backups = config.backup.max_backups

    # 获取所有备份，按创建时间降序排列
    backups = db.query(ConfigBackup).order_by(ConfigBackup.created_at.desc()).all()

    # 如果备份数量超过限制，删除多余的
    if len(backups) > max_backups:
        backups_to_delete = backups[max_backups:]

        for backup in backups_to_delete:
            # 删除备份文件
            backup_path = Path(backup.file_path)
            if backup_path.exists():
                try:
                    if backup_path.is_dir():
                        shutil.rmtree(backup_path, ignore_errors=True)
                    else:
                        backup_path.unlink()
                except Exception:
                    pass

            # 删除数据库记录
            db.delete(backup)

        db.commit()


def delete_backup(db: Session, backup_id: int) -> bool:
    """
    删除指定备份

    Args:
        db: 数据库会话
        backup_id: 备份ID

    Returns:
        bool: 是否成功
    """
    backup = get_backup(db, backup_id)
    if not backup:
        return False

    # 删除备份文件
    backup_path = Path(backup.file_path)
    if backup_path.exists():
        try:
            if backup_path.is_dir():
                shutil.rmtree(backup_path, ignore_errors=True)
            else:
                backup_path.unlink()
        except Exception:
            pass

    # 删除数据库记录
    db.delete(backup)
    db.commit()

    return True
