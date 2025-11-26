"""
数据库连接和初始化模块
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
import bcrypt
from datetime import datetime
from typing import Optional

from app.config import get_config
from app.models import Base, User, ConfigBackup, OperationLog, Certificate


# 数据库文件路径
DB_DIR = Path(__file__).parent.parent / "data"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "app.db"

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

