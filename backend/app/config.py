"""
配置管理模块
读取 config.yaml 配置文件并提供配置访问接口
"""
import os
import yaml
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from functools import lru_cache


class NginxConfig(BaseModel):
    """Nginx 相关配置"""
    config_path: str = "/etc/nginx/nginx.conf"
    executable: str = "/usr/sbin/nginx"
    static_dir: str = "/usr/share/nginx/html"
    log_dir: str = "/var/log/nginx"
    conf_dir: str = "/etc/nginx/conf.d"
    access_log: str = "/var/log/nginx/access.log"
    error_log: str = "/var/log/nginx/error.log"
    ssl_dir: str = "/etc/nginx/ssl"
    certbot_path: str = "/usr/bin/certbot"
    # Nginx 多版本管理相关目录
    versions_root: str = "/app/nginx/versions"
    build_root: str = "/app/nginx/build"
    build_logs_dir: str = "/app/nginx/build_logs"


class AppConfig(BaseModel):
    """应用配置"""
    host: str = "127.0.0.1"
    port: int = 8000
    secret_key: Optional[str] = None
    debug: bool = False  # 调试模式，启用自动重载


class BackupConfig(BaseModel):
    """备份配置"""
    max_backups: int = 10
    backup_dir: str = "./data/backups"


class Config(BaseModel):
    """全局配置"""
    nginx: NginxConfig = Field(default_factory=NginxConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认为 backend/config.yaml
        """
        if config_path is None:
            # 获取项目根目录
            current_dir = Path(__file__).parent.parent
            config_path = current_dir / "config.yaml"
        
        self.config_path = Path(config_path)
        self._config: Optional[Config] = None
        self.load_config()
    
    def load_config(self) -> Config:
        """加载配置文件"""
        # 如果配置文件存在，读取它
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f) or {}
        else:
            config_data = {}
        
        # 从环境变量覆盖配置
        nginx_config = config_data.get('nginx', {})
        app_config = config_data.get('app', {})
        backup_config = config_data.get('backup', {})
        
        # 环境变量覆盖
        nginx_config['config_path'] = os.getenv('NGINX_CONFIG_PATH', nginx_config.get('config_path', '/etc/nginx/nginx.conf'))
        nginx_config['executable'] = os.getenv('NGINX_EXECUTABLE', nginx_config.get('executable', '/usr/sbin/nginx'))
        nginx_config['static_dir'] = os.getenv('NGINX_STATIC_DIR', nginx_config.get('static_dir', '/usr/share/nginx/html'))
        nginx_config['log_dir'] = os.getenv('NGINX_LOG_DIR', nginx_config.get('log_dir', '/var/log/nginx'))
        nginx_config['conf_dir'] = os.getenv('NGINX_CONF_DIR', nginx_config.get('conf_dir', '/etc/nginx/conf.d'))
        nginx_config['access_log'] = os.getenv('NGINX_ACCESS_LOG', nginx_config.get('access_log', '/var/log/nginx/access.log'))
        nginx_config['error_log'] = os.getenv('NGINX_ERROR_LOG', nginx_config.get('error_log', '/var/log/nginx/error.log'))
        nginx_config['ssl_dir'] = os.getenv('NGINX_SSL_DIR', nginx_config.get('ssl_dir', '/etc/nginx/ssl'))
        nginx_config['certbot_path'] = os.getenv('CERTBOT_PATH', nginx_config.get('certbot_path', '/usr/bin/certbot'))
        # 多版本 Nginx 管理相关目录，可通过环境变量覆盖
        nginx_config['versions_root'] = os.getenv('NGINX_VERSIONS_ROOT', nginx_config.get('versions_root', '/app/nginx/versions'))
        nginx_config['build_root'] = os.getenv('NGINX_BUILD_ROOT', nginx_config.get('build_root', '/app/nginx/build'))
        nginx_config['build_logs_dir'] = os.getenv('NGINX_BUILD_LOGS_DIR', nginx_config.get('build_logs_dir', '/app/nginx/build_logs'))
        
        app_config['host'] = os.getenv('APP_HOST', app_config.get('host', '127.0.0.1'))
        app_config['port'] = int(os.getenv('APP_PORT', app_config.get('port', 8000)))
        app_config['secret_key'] = os.getenv('SECRET_KEY', app_config.get('secret_key'))
        # 调试模式：可通过环境变量 DEBUG 或配置文件设置
        debug_env = os.getenv('DEBUG', '').lower() in ('true', '1', 'yes')
        app_config['debug'] = debug_env or app_config.get('debug', False)
        
        backup_config['max_backups'] = int(os.getenv('MAX_BACKUPS', backup_config.get('max_backups', 10)))
        backup_config['backup_dir'] = os.getenv('BACKUP_DIR', backup_config.get('backup_dir', './data/backups'))
        
        self._config = Config(
            nginx=NginxConfig(**nginx_config),
            app=AppConfig(**app_config),
            backup=BackupConfig(**backup_config)
        )
        
        # 确保备份目录存在
        backup_dir = Path(self._config.backup.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        return self._config
    
    @property
    def config(self) -> Config:
        """获取配置对象"""
        if self._config is None:
            self.load_config()
        return self._config
    
    def reload(self) -> Config:
        """重新加载配置"""
        return self.load_config()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


@lru_cache()
def get_config() -> Config:
    """获取配置实例（单例模式）"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.config


def reload_config() -> Config:
    """重新加载配置"""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager.reload()

