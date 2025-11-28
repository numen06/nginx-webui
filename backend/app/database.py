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

from app.models import Base, User, ConfigBackup, OperationLog, Certificate, GitRepository


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


def init_db():
    """初始化数据库，创建所有表"""
    Base.metadata.create_all(bind=engine)
    
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
                created_at=datetime.utcnow()
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

