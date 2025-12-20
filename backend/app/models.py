"""
数据库模型定义
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    """用户模型"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # 关联关系
    operation_logs = relationship("OperationLog", back_populates="user")
    config_backups = relationship("ConfigBackup", back_populates="creator")
    certificates = relationship("Certificate", back_populates="creator")


class ConfigBackup(Base):
    """配置文件备份模型"""
    __tablename__ = "config_backups"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_last_version = Column(Boolean, default=False, nullable=False, index=True)  # 标记是否为最后版本
    
    # 关联关系
    creator = relationship("User", back_populates="config_backups")


class OperationLog(Base):
    """操作日志模型"""
    __tablename__ = "operation_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String(50), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)  # 操作类型
    target = Column(String(500), nullable=True)  # 操作目标
    details = Column(Text, nullable=True)  # 操作详情（JSON 格式）
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    # 关联关系
    user = relationship("User", back_populates="operation_logs")


class Certificate(Base):
    """证书模型"""
    __tablename__ = "certificates"
    
    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), nullable=False, index=True)
    cert_path = Column(String(500), nullable=False)
    key_path = Column(String(500), nullable=False)
    issuer = Column(String(255), nullable=True)  # 证书颁发者（如 Let's Encrypt）
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True, index=True)
    auto_renew = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # 关联关系
    creator = relationship("User", back_populates="certificates")


class GitRepository(Base):
    """Git 仓库配置"""
    __tablename__ = "git_repositories"

    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String(255), unique=True, nullable=False, index=True)
    repo_url = Column(String(500), nullable=False)
    username = Column(String(255), nullable=True)
    password = Column(String(255), nullable=True)
    branch = Column(String(255), nullable=False, default="main")
    last_synced_at = Column(DateTime, nullable=True)
    last_sync_status = Column(String(50), nullable=True)
    last_sync_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
    )


class StatisticsCache(Base):
    """统计数据缓存（1小时、1天等整数小时范围）- 旧表，保留兼容"""
    __tablename__ = "statistics_cache"

    id = Column(Integer, primary_key=True, index=True)
    time_range_hours = Column(Integer, nullable=False, index=True)
    cache_key = Column(String(100), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    last_log_position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class StatisticsCache5Min(Base):
    """5分钟统计数据缓存（单独表）- 旧表，保留兼容"""
    __tablename__ = "statistics_cache_5min"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(100), unique=True, nullable=False, index=True)
    data = Column(Text, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    last_log_position = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


# 新的统计架构：按时间粒度分表存储，支持SQL聚合
class Statistics5Min(Base):
    """5分钟粒度统计（如7:00-7:05）"""
    __tablename__ = "statistics_5min"

    id = Column(Integer, primary_key=True, index=True)
    time_bucket = Column(DateTime, unique=True, nullable=False, index=True)  # 时间桶：YYYY-MM-DD HH:mm:00
    
    # 基础统计
    total_requests = Column(Integer, default=0)
    success_requests = Column(Integer, default=0)
    error_requests = Column(Integer, default=0)
    attack_count = Column(Integer, default=0)
    error_log_count = Column(Integer, default=0)  # 错误日志数量
    
    # 详细数据（JSON）
    status_distribution = Column(Text, nullable=True)  # {"200": 100, "404": 20}
    method_distribution = Column(Text, nullable=True)  # {"GET": 80, "POST": 20}
    top_ips = Column(Text, nullable=True)  # [{"ip": "1.2.3.4", "count": 10}]
    top_paths = Column(Text, nullable=True)  # [{"path": "/api", "count": 50}]
    attacks = Column(Text, nullable=True)  # 攻击记录
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class StatisticsHourly(Base):
    """小时粒度统计（如7:00-8:00）"""
    __tablename__ = "statistics_hourly"

    id = Column(Integer, primary_key=True, index=True)
    time_bucket = Column(DateTime, unique=True, nullable=False, index=True)  # 时间桶：YYYY-MM-DD HH:00:00
    
    # 基础统计
    total_requests = Column(Integer, default=0)
    success_requests = Column(Integer, default=0)
    error_requests = Column(Integer, default=0)
    attack_count = Column(Integer, default=0)
    
    # 详细数据（JSON）
    status_distribution = Column(Text, nullable=True)
    method_distribution = Column(Text, nullable=True)
    top_ips = Column(Text, nullable=True)
    top_paths = Column(Text, nullable=True)
    attacks = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)


class StatisticsDaily(Base):
    """天粒度统计（如2025-12-02）"""
    __tablename__ = "statistics_daily"

    id = Column(Integer, primary_key=True, index=True)
    time_bucket = Column(DateTime, unique=True, nullable=False, index=True)  # 时间桶：YYYY-MM-DD 00:00:00
    
    # 基础统计
    total_requests = Column(Integer, default=0)
    success_requests = Column(Integer, default=0)
    error_requests = Column(Integer, default=0)
    attack_count = Column(Integer, default=0)
    
    # 详细数据（JSON）
    status_distribution = Column(Text, nullable=True)
    method_distribution = Column(Text, nullable=True)
    top_ips = Column(Text, nullable=True)
    top_paths = Column(Text, nullable=True)
    attacks = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

