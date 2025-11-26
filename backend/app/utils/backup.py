"""
配置备份工具
"""
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.config import get_config
from app.models import ConfigBackup
from app.utils.nginx import get_config_path


def create_backup(db: Session, created_by_id: Optional[int] = None) -> ConfigBackup:
    """
    创建配置文件备份
    
    Args:
        db: 数据库会话
        created_by_id: 创建者用户ID
    
    Returns:
        ConfigBackup: 备份记录
    """
    # 备份当前实际使用的 Nginx 配置文件，而不是固定的 config.yaml 路径
    # 这样在多版本 Nginx 管理启用时，备份/恢复都严格基于“活动版本”的 nginx.conf。
    config = get_config()
    config_path = get_config_path()
    backup_dir = Path(config.backup.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    
    # 生成备份文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"nginx.conf.backup.{timestamp}"
    backup_path = backup_dir / backup_filename
    
    # 复制配置文件
    shutil.copy2(config_path, backup_path)
    
    # 创建备份记录
    backup_record = ConfigBackup(
        filename=backup_filename,
        file_path=str(backup_path),
        created_by_id=created_by_id,
        created_at=datetime.utcnow()
    )
    db.add(backup_record)
    db.commit()
    db.refresh(backup_record)
    
    # 清理旧备份
    cleanup_old_backups(db)
    
    return backup_record


def list_backups(db: Session, limit: Optional[int] = None) -> List[ConfigBackup]:
    """
    列出所有备份
    
    Args:
        db: 数据库会话
        limit: 限制返回数量
    
    Returns:
        List[ConfigBackup]: 备份列表
    """
    query = db.query(ConfigBackup).order_by(ConfigBackup.created_at.desc())
    if limit:
        query = query.limit(limit)
    return query.all()


def get_backup(db: Session, backup_id: int) -> Optional[ConfigBackup]:
    """获取指定备份"""
    return db.query(ConfigBackup).filter(ConfigBackup.id == backup_id).first()


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
        return False
    
    # 恢复到当前应使用的配置文件路径（与 create_backup 一致）
    config_path = get_config_path()
    
    # 恢复备份前先创建当前配置的备份
    try:
        create_backup(db, created_by_id=backup.created_by_id)
    except Exception:
        pass  # 如果备份失败，继续恢复
    
    # 复制备份文件到配置文件位置
    shutil.copy2(backup_path, config_path)
    
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
            backup_path.unlink()
        except Exception:
            pass
    
    # 删除数据库记录
    db.delete(backup)
    db.commit()
    
    return True

