"""
数据库连接和初始化模块
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import bcrypt
import os
from datetime import datetime
from typing import Optional

from app.models import (
    Base,
    User,
    ConfigBackup,
    OperationLog,
    Certificate,
    GitRepository,
    StatisticsCache,
    DynamicService,
    DynamicServiceInstance,
)
from sqlalchemy import inspect, text


def _safe_mkdir(path: Path) -> None:
    """安全地创建目录，处理挂载点等特殊情况"""
    if path.exists():
        return
    
    try:
        # 尝试直接创建
        path.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, OSError):
        # 如果失败，逐级创建（从根到目标）
        try:
            # path.parents 是从根到目标父目录的顺序，需要反转
            parents_list = list(path.parents)
            parents_list.reverse()  # 从根目录开始
            for parent in parents_list:
                if not parent.exists():
                    try:
                        parent.mkdir(exist_ok=True)
                    except (FileExistsError, OSError):
                        # 忽略父目录创建错误，继续尝试
                        pass
            # 最后创建目标目录
            if not path.exists():
                path.mkdir(exist_ok=True)
        except (FileExistsError, OSError):
            # 如果仍然失败，可能是挂载点或权限问题，忽略错误
            pass


def _get_db_path() -> Path:
    """获取数据库文件路径，使用环境变量 DATA_ROOT（避免循环依赖）"""
    # 直接从环境变量获取，不依赖 get_config()，避免循环依赖
    data_root = os.getenv("DATA_ROOT", "/app/data").rstrip("/")
    db_dir = Path(data_root) / "backend"
    
    # 安全地创建目录
    _safe_mkdir(db_dir)
    
    return db_dir / "app.db"


# 数据库文件路径
DB_PATH = _get_db_path()

# SQLite 数据库连接字符串
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# 创建数据库引擎
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite 需要这个参数
    echo=False  # 设置为 True 可以打印所有 SQL 语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _migrate_add_is_last_version():
    """迁移：为 config_backups 表添加 is_last_version 字段"""
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('config_backups')]
        
        if 'is_last_version' not in columns:
            # 添加新列
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE config_backups ADD COLUMN is_last_version BOOLEAN DEFAULT 0 NOT NULL"))
                conn.commit()
            print("已为 config_backups 表添加 is_last_version 字段")
    except Exception as e:
        # 如果表不存在，会在 create_all 时创建，这里忽略错误
        if "no such table" not in str(e).lower():
            print(f"迁移 is_last_version 字段时出错: {e}")
    finally:
        db.close()


def _migrate_add_certbot_cert_name():
    """迁移：为 certificates 表添加 certbot_cert_name 字段"""
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        if not inspector.has_table("certificates"):
            return
        columns = [col["name"] for col in inspector.get_columns("certificates")]

        if "certbot_cert_name" not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE certificates ADD COLUMN certbot_cert_name VARCHAR(255)"))
                conn.commit()
            print("已为 certificates 表添加 certbot_cert_name 字段")
    except Exception as e:
        if "no such table" not in str(e).lower():
            print(f"迁移 certbot_cert_name 字段时出错: {e}")
    finally:
        db.close()


def _migrate_add_certificate_issue_fields():
    """迁移：为 certificates 表添加 DNS 自动签发状态字段"""
    db = SessionLocal()
    try:
        inspector = inspect(engine)
        if not inspector.has_table("certificates"):
            return
        columns = [col["name"] for col in inspector.get_columns("certificates")]
        migrations = [
            ("status", "ALTER TABLE certificates ADD COLUMN status VARCHAR(50) DEFAULT 'issued' NOT NULL"),
            ("issue_method", "ALTER TABLE certificates ADD COLUMN issue_method VARCHAR(20)"),
            ("dns_job_id", "ALTER TABLE certificates ADD COLUMN dns_job_id VARCHAR(64)"),
            ("dns_record_name", "ALTER TABLE certificates ADD COLUMN dns_record_name VARCHAR(255)"),
            ("dns_record_value", "ALTER TABLE certificates ADD COLUMN dns_record_value TEXT"),
            ("dns_challenge_count", "ALTER TABLE certificates ADD COLUMN dns_challenge_count INTEGER DEFAULT 1 NOT NULL"),
            ("dns_auto_issue", "ALTER TABLE certificates ADD COLUMN dns_auto_issue BOOLEAN DEFAULT 0 NOT NULL"),
            ("dns_email", "ALTER TABLE certificates ADD COLUMN dns_email VARCHAR(255)"),
            ("issue_error", "ALTER TABLE certificates ADD COLUMN issue_error TEXT"),
            ("issue_output", "ALTER TABLE certificates ADD COLUMN issue_output TEXT"),
            ("updated_at", "ALTER TABLE certificates ADD COLUMN updated_at DATETIME"),
        ]

        with engine.connect() as conn:
            changed = False
            for column_name, sql in migrations:
                if column_name not in columns:
                    conn.execute(text(sql))
                    changed = True
            if changed:
                conn.execute(
                    text(
                        "UPDATE certificates SET updated_at = created_at "
                        "WHERE updated_at IS NULL"
                    )
                )
                conn.commit()
                print("已为 certificates 表添加证书签发状态字段")
    except Exception as e:
        if "no such table" not in str(e).lower():
            print(f"迁移证书签发状态字段时出错: {e}")
    finally:
        db.close()


def _migrate_add_user_admin():
    """迁移：增加管理员标记，并将超级管理员收敛为唯一账户。"""
    try:
        inspector = inspect(engine)
        if not inspector.has_table("users"):
            return
        columns = [col["name"] for col in inspector.get_columns("users")]
        with engine.begin() as conn:
            if "is_admin" not in columns:
                conn.execute(
                    text(
                        "ALTER TABLE users ADD COLUMN is_admin BOOLEAN "
                        "DEFAULT 0 NOT NULL"
                    )
                )
            admin_count = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE is_admin = 1 AND is_active = 1")
            ).scalar_one()
            if not admin_count:
                fallback_id = conn.execute(
                    text(
                        "SELECT id FROM users WHERE is_active = 1 "
                        "ORDER BY CASE WHEN username = 'admin' THEN 0 ELSE 1 END, "
                        "created_at ASC, id ASC LIMIT 1"
                    )
                ).scalar_one_or_none()
                if fallback_id is not None:
                    conn.execute(
                        text("UPDATE users SET is_admin = 1 WHERE id = :user_id"),
                        {"user_id": fallback_id},
                    )
            keeper_id = conn.execute(
                text(
                    "SELECT id FROM users WHERE is_admin = 1 "
                    "ORDER BY is_active DESC, "
                    "CASE WHEN username = 'admin' THEN 0 ELSE 1 END, "
                    "created_at ASC, id ASC LIMIT 1"
                )
            ).scalar_one_or_none()
            if keeper_id is not None:
                conn.execute(
                    text("UPDATE users SET is_admin = 0 WHERE id != :user_id"),
                    {"user_id": keeper_id},
                )
            conn.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_single_admin "
                    "ON users(is_admin) WHERE is_admin = 1"
                )
            )
    except Exception as e:
        if "no such table" not in str(e).lower():
            print(f"迁移 users.is_admin 字段时出错: {e}")


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)
    
    # 执行迁移
    _migrate_add_is_last_version()
    _migrate_add_certbot_cert_name()
    _migrate_add_certificate_issue_fields()
    _migrate_add_user_admin()
    
    # 创建默认管理员账户（如果不存在）
    db = SessionLocal()
    try:
        admin_user = db.query(User).filter(User.username == "admin").first()
        if not admin_user:
            # 默认密码为 "admin"，首次登录后应修改
            password_hash = bcrypt.hashpw("admin".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            admin_user = User(
                username="admin",
                password_hash=password_hash,
                is_active=True,
                is_admin=True,
                created_at=datetime.now()
            )
            db.add(admin_user)
            db.commit()
            print("默认管理员账户已创建: admin/admin (首次登录后请修改密码)")
    except Exception as e:
        print(f"初始化默认用户时出错: {e}")
        db.rollback()
    finally:
        db.close()


def get_db():
    """
    获取数据库会话
    
    Usage:
        db = next(get_db())
        try:
            # 使用 db
            pass
        finally:
            db.close()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def reset_db():
    """重置数据库（删除所有表并重新创建）"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    init_db()
