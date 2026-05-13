# Nginx WebUI Code Wiki

## 📋 项目概述

**Nginx WebUI** 是一个基于Web界面的Nginx管理工具，提供配置管理、证书管理、日志分析、系统监控等功能。

### 核心功能模块
- **配置管理**：图形化编辑Nginx配置文件
- **证书管理**：Let's Encrypt证书申请和自动续期
- **日志分析**：访问日志和错误日志分析
- **系统监控**：Nginx运行状态和性能监控
- **文件管理**：Nginx配置文件的上传下载
- **Git集成**：配置文件的版本控制

---

## 🏗️ 项目架构

### 技术栈

#### 后端技术
- **框架**：FastAPI (异步Web框架)
- **ORM**：SQLAlchemy (数据库ORM)
- **验证**：Pydantic (数据验证)
- **服务器**：Uvicorn (ASGI服务器)
- **数据库**：SQLite (默认), 支持PostgreSQL/MySQL
- **证书**：Certbot (Let's Encrypt)

#### 前端技术
- **框架**：Vue 3 (组合式API)
- **路由**：Vue Router 4
- **状态管理**：Pinia
- **UI组件库**：Element Plus
- **构建工具**：Vite
- **图表库**：ECharts
- **代码编辑器**：Monaco Editor

### 系统架构图

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue 3)                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  │
│  │Dashboard│  │ Config  │  │  Cert   │  │  Log    │  │
│  │  仪表盘  │  │  配置   │  │  证书   │  │  日志   │  │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  │
└───────┼────────────┼────────────┼────────────┼───────┘
        │            │            │            │
        └────────────┴─────┬──────┴────────────┘
                            │
                    ┌───────┴───────┐
                    │   REST API    │
                    │  (FastAPI)    │
                    └───────┬───────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────┴───────┐   ┌───────┴───────┐   ┌───────┴───────┐
│   数据层       │   │   业务逻辑层   │   │   外部系统    │
│ (SQLAlchemy)  │   │   (Services)  │   │   (Nginx等)   │
│   SQLite      │   │               │   │               │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

## 📁 目录结构

```
nginx-webui/
├── backend/                    # 后端应用
│   ├── main.py                 # 应用入口
│   ├── config.py               # 配置管理
│   ├── database.py             # 数据库连接
│   ├── models.py               # 数据模型
│   ├── requirements.txt        # Python依赖
│   ├── routers/                # API路由
│   │   ├── __init__.py
│   │   ├── admin.py            # 管理员相关
│   │   ├── backup.py           # 备份管理
│   │   ├── cert.py             # 证书管理
│   │   ├── config.py           # 配置管理
│   │   ├── git_repo.py         # Git仓库
│   │   ├── log.py              # 日志分析
│   │   ├── nginx.py            # Nginx操作
│   │   ├── permission.py       # 权限管理
│   │   ├── statistics.py       # 统计分析
│   │   ├── system.py           # 系统信息
│   │   ├── token.py            # Token管理
│   │   └── user.py             # 用户管理
│   ├── schemas/                # Pydantic模型
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── backup.py
│   │   ├── cert.py
│   │   ├── config.py
│   │   ├── git_repo.py
│   │   ├── log.py
│   │   ├── nginx.py
│   │   ├── permission.py
│   │   ├── statistics.py
│   │   ├── system.py
│   │   ├── token.py
│   │   └── user.py
│   ├── services/               # 业务逻辑层
│   │   ├── __init__.py
│   │   ├── backup_service.py
│   │   ├── cert_service.py
│   │   ├── config_service.py
│   │   ├── git_service.py
│   │   ├── log_service.py
│   │   ├── nginx_service.py
│   │   ├── permission_service.py
│   │   ├── statistics_service.py
│   │   ├── system_service.py
│   │   ├── task_service.py
│   │   ├── token_service.py
│   │   └── user_service.py
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── ai_utils.py         # AI相关工具
│       ├── certbot.py          # Certbot封装
│       ├── crontab.py          # 定时任务
│       ├── file_utils.py       # 文件操作
│       ├── git_utils.py        # Git操作
│       ├── log_utils.py        # 日志工具
│       ├── nginx_utils.py      # Nginx操作
│       ├── privilege.py        # 权限检查
│       ├── report_utils.py     # 报告生成
│       ├── system_utils.py     # 系统工具
│       └── zip_utils.py        # 压缩工具
│
├── frontend/                   # 前端应用
│   ├── public/                 # 静态资源
│   ├── src/                    # 源代码
│   │   ├── main.js            # 入口文件
│   │   ├── App.vue            # 根组件
│   │   ├── api/               # API调用
│   │   │   ├── index.js
│   │   │   ├── config.js
│   │   │   ├── cert.js
│   │   │   ├── log.js
│   │   │   ├── nginx.js
│   │   │   ├── system.js
│   │   │   ├── user.js
│   │   │   └── statistics.js
│   │   ├── components/        # 公共组件
│   │   │   ├── FileManager.vue
│   │   │   ├── LogViewer.vue
│   │   │   └── MonacoEditor.vue
│   │   ├── layouts/           # 布局组件
│   │   │   ├── IndexLayout.vue
│   │   │   └── LoginLayout.vue
│   │   ├── router/            # 路由配置
│   │   │   └── index.js
│   │   ├── stores/            # 状态管理
│   │   │   ├── index.js
│   │   │   └── user.js
│   │   └── views/             # 页面组件
│   │       ├── Dashboard.vue
│   │       ├── Config.vue
│   │       ├── Log.vue
│   │       ├── Cert.vue
│   │       ├── System.vue
│   │       ├── GitRepo.vue
│   │       ├── Backup.vue
│   │       ├── Statistics.vue
│   │       ├── User.vue
│   │       ├── Permission.vue
│   │       └── Login.vue
│   ├── package.json
│   ├── vite.config.js
│   └── index.html
│
├── wiki/                      # 项目文档
├── config.yaml                # 配置文件
├── docker-compose.yml         # Docker编排
├── Dockerfile                 # Docker镜像
└── README.md                  # 项目说明
```

---

## 🔌 后端模块详解

### 核心模块

#### 1. main.py - 应用入口
**职责**：FastAPI应用初始化、路由注册、中间件配置

**关键代码**：
```python
# 应用初始化
app = FastAPI(title="Nginx WebUI")

# 路由注册
app.include_router(router, prefix="/api")

# 启动事件
@app.on_event("startup")
async def startup():
    # 初始化数据库
    init_db()
    # 启动定时任务
    start_cron_tasks()
```

#### 2. config.py - 配置管理
**职责**：配置文件读取和环境变量管理

**关键配置项**：
```python
# Nginx配置
nginx_bin: str = "/usr/sbin/nginx"  # Nginx可执行文件路径
nginx_conf: str = "/etc/nginx/nginx.conf"  # 配置文件路径

# 数据库配置
db_url: str = "sqlite:///./nginx_webui.db"  # 数据库连接URL

# 安全配置
secret_key: str  # JWT密钥
token_expire_minutes: int = 60  # Token过期时间

# Certbot配置
certbot_path: str = "/opt/certbot/certbot"  # Certbot路径
letsencrypt_email: str  # Let's Encrypt注册邮箱
```

#### 3. database.py - 数据库连接
**职责**：SQLAlchemy数据库引擎和会话管理

**关键类**：
```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 创建引擎
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()

# 获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

#### 4. models.py - 数据模型
**职责**：SQLAlchemy ORM模型定义

**主要数据表**：

| 表名 | 说明 | 关键字段 |
|------|------|---------|
| User | 用户表 | id, username, password_hash, email, role, status |
| ConfigBackup | 配置备份 | id, name, content, backup_type, created_by, created_at |
| AuditLog | 审计日志 | id, user_id, action, resource, details, ip_address, created_at |
| Certificate | SSL证书 | id, domain, cert_path, key_path, created_at, expire_at |
| GitRepo | Git仓库 | id, name, path, remote_url, branch |
| Statistics | 统计数据 | id, metric_type, value, timestamp |

---

### API路由模块

#### 1. admin.py - 管理员API
**端点**：
```
GET    /api/admin/status          # 获取系统状态
POST   /api/admin/backup          # 创建备份
GET    /api/admin/restore/{id}    # 恢复备份
DELETE /api/admin/backup/{id}     # 删除备份
```

#### 2. config.py - 配置管理API
**端点**：
```
GET    /api/config/file           # 获取配置文件内容
POST   /api/config/file           # 保存配置文件
GET    /api/config/diff           # 查看配置差异
POST   /api/config/reload         # 重载Nginx配置
```

#### 3. cert.py - 证书管理API
**端点**：
```
GET    /api/cert/list             # 获取证书列表
POST   /api/cert/apply            # 申请新证书
POST   /api/cert/renew/{id}       # 续期证书
DELETE /api/cert/{id}             # 删除证书
GET    /api/cert/info/{id}        # 获取证书详情
```

#### 4. nginx.py - Nginx操作API
**端点**：
```
GET    /api/nginx/status          # 获取Nginx状态
POST   /api/nginx/start           # 启动Nginx
POST   /api/nginx/stop            # 停止Nginx
POST   /api/nginx/reload          # 重载Nginx
GET    /api/nginx/config/test     # 测试配置文件
```

#### 5. log.py - 日志分析API
**端点**：
```
GET    /api/log/access            # 获取访问日志
GET    /api/log/error             # 获取错误日志
POST   /api/log/analyze           # 分析日志数据
GET    /api/log/stats             # 获取日志统计
```

#### 6. user.py - 用户管理API
**端点**：
```
POST   /api/user/login            # 用户登录
POST   /api/user/logout           # 用户登出
GET    /api/user/list             # 获取用户列表
POST   /api/user/create           # 创建用户
PUT    /api/user/{id}             # 更新用户
DELETE /api/user/{id}             # 删除用户
```

#### 7. system.py - 系统信息API
**端点**：
```
GET    /api/system/info           # 获取系统信息
GET    /api/system/disk           # 获取磁盘使用
GET    /api/system/memory         # 获取内存使用
GET    /api/system/cpu             # 获取CPU使用
```

#### 8. statistics.py - 统计API
**端点**：
```
GET    /api/statistics/overview  # 获取统计概览
GET    /api/statistics/daily     # 获取每日统计
GET    /api/statistics/weekly    # 获取每周统计
GET    /api/statistics/monthly   # 获取每月统计
```

#### 9. backup.py - 备份管理API
**端点**：
```
GET    /api/backup/list           # 获取备份列表
POST   /api/backup/create         # 创建备份
POST   /api/backup/restore/{id}   # 恢复备份
DELETE /api/backup/{id}           # 删除备份
```

#### 10. permission.py - 权限管理API
**端点**：
```
GET    /api/permission/list       # 获取权限列表
POST   /api/permission/assign     # 分配权限
DELETE /api/permission/{id}      # 删除权限
```

#### 11. git_repo.py - Git仓库API
**端点**：
```
GET    /api/git/repos             # 获取仓库列表
POST   /api/git/clone             # 克隆仓库
POST   /api/git/commit           # 提交更改
POST   /api/git/push             # 推送到远程
GET    /api/git/log              # 获取提交历史
```

---

### 工具模块 (utils/)

#### 1. nginx_utils.py - Nginx操作工具
**职责**：封装Nginx命令行操作

**关键函数**：
```python
def check_nginx_installed() -> bool
def start_nginx() -> bool
def stop_nginx() -> bool
def reload_nginx() -> bool
def test_config() -> tuple[bool, str]
def get_nginx_status() -> dict
def get_nginx_version() -> str
```

#### 2. certbot.py - Certbot封装
**职责**：封装Certbot证书申请和续期操作

**关键函数**：
```python
def check_certbot_installed() -> bool
def apply_cert(domain: str, email: str, webroot: str) -> bool
def renew_cert(domain: str) -> bool
def revoke_cert(domain: str) -> bool
def get_cert_info(domain: str) -> dict
```

#### 3. git_utils.py - Git操作工具
**职责**：封装Git命令行操作

**关键函数**：
```python
def check_git_installed() -> bool
def clone_repo(url: str, path: str) -> bool
def commit_changes(path: str, message: str) -> bool
def push_changes(path: str) -> bool
def pull_changes(path: str) -> bool
def get_git_log(path: str, limit: int = 10) -> list
```

#### 4. crontab.py - 定时任务管理
**职责**：管理系统定时任务

**关键函数**：
```python
def add_cron_job(command: str, schedule: str) -> bool
def remove_cron_job(job_id: str) -> bool
def list_cron_jobs() -> list
def enable_cron_job(job_id: str) -> bool
def disable_cron_job(job_id: str) -> bool
```

#### 5. system_utils.py - 系统工具
**职责**：系统信息收集和监控

**关键函数**：
```python
def get_system_info() -> dict
def get_cpu_usage() -> float
def get_memory_usage() -> dict
def get_disk_usage() -> dict
def get_network_stats() -> dict
def get_process_list() -> list
```

#### 6. log_utils.py - 日志工具
**职责**：日志文件读取和分析

**关键函数**：
```python
def read_log_file(path: str, lines: int = 100) -> list
def parse_access_log(line: str) -> dict
def parse_error_log(line: str) -> dict
def analyze_log_stats(log_data: list) -> dict
def get_log_summary(path: str) -> dict
```

#### 7. file_utils.py - 文件操作工具
**职责**：文件和目录操作

**关键函数**：
```python
def read_file(path: str) -> str
def write_file(path: str, content: str) -> bool
def copy_file(src: str, dst: str) -> bool
def delete_file(path: str) -> bool
def create_directory(path: str) -> bool
def list_directory(path: str) -> list
```

#### 8. zip_utils.py - 压缩工具
**职责**：文件和目录压缩

**关键函数**：
```python
def zip_directory(source_dir: str, output_file: str) -> bool
def unzip_file(zip_file: str, extract_to: str) -> bool
def create_tarball(source_dir: str, output_file: str) -> bool
```

---

## 🎨 前端模块详解

### 入口文件

#### main.js - 应用入口
**职责**：Vue应用初始化和全局配置

```javascript
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import router from './router'
import App from './App.vue'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

app.mount('#app')
```

#### App.vue - 根组件
**职责**：应用根组件，包含路由视图

```vue
<template>
  <router-view />
</template>

<script setup>
// 全局样式和配置
</script>
```

### 路由配置 (router/index.js)

**职责**：路由定义和导航守卫

```javascript
const routes = [
  {
    path: '/login',
    component: () => import('../layouts/LoginLayout.vue'),
    children: [
      { path: '', name: 'Login', component: () => import('../views/Login.vue') }
    ]
  },
  {
    path: '/',
    component: () => import('../layouts/IndexLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'Dashboard', component: () => import('../views/Dashboard.vue') },
      { path: 'config', name: 'Config', component: () => import('../views/Config.vue') },
      { path: 'cert', name: 'Cert', component: () => import('../views/Cert.vue') },
      { path: 'log', name: 'Log', component: () => import('../views/Log.vue') },
      { path: 'system', name: 'System', component: () => import('../views/System.vue') },
      { path: 'git', name: 'GitRepo', component: () => import('../views/GitRepo.vue') },
      { path: 'backup', name: 'Backup', component: () => import('../views/Backup.vue') },
      { path: 'statistics', name: 'Statistics', component: () => import('../views/Statistics.vue') },
      { path: 'user', name: 'User', component: () => import('../views/User.vue') },
      { path: 'permission', name: 'Permission', component: () => import('../views/Permission.vue') }
    ]
  }
]
```

### 主要页面组件

#### 1. Dashboard.vue - 仪表盘
**职责**：系统状态总览和快速操作

**功能模块**：
- Nginx运行状态显示
- 系统资源监控（CPU、内存、磁盘）
- 快速操作按钮
- 统计图表展示

#### 2. Config.vue - 配置管理
**职责**：Nginx配置文件编辑

**功能模块**：
- 配置文件树形列表
- Monaco Editor代码编辑器
- 语法高亮和自动补全
- 配置验证和保存
- 配置差异对比

#### 3. Cert.vue - 证书管理
**职责**：SSL证书申请和管理

**功能模块**：
- 证书列表展示
- 证书申请向导
- 证书续期管理
- 证书详情查看
- 自动续期设置

#### 4. Log.vue - 日志分析
**职责**：访问日志和错误日志分析

**功能模块**：
- 日志文件列表
- 实时日志查看
- 日志搜索和过滤
- 日志统计图表
- 日志导出功能

#### 5. System.vue - 系统信息
**职责**：服务器系统信息展示

**功能模块**：
- 系统基本信息
- 资源使用情况
- 进程管理
- 服务管理
- 网络连接状态

#### 6. Statistics.vue - 统计分析
**职责**：流量和性能统计分析

**功能模块**：
- 访问量趋势图
- 带宽使用统计
- 请求类型分布
- 响应时间分析
- TOP访问页面

### API模块 (api/)

#### config.js - 配置API
```javascript
export function getConfigFile(path) {
  return axios.get(`/api/config/file?path=${path}`)
}

export function saveConfigFile(data) {
  return axios.post('/api/config/file', data)
}

export function reloadNginx() {
  return axios.post('/api/config/reload')
}
```

#### cert.js - 证书API
```javascript
export function getCertList() {
  return axios.get('/api/cert/list')
}

export function applyCert(data) {
  return axios.post('/api/cert/apply', data)
}

export function renewCert(id) {
  return axios.post(`/api/cert/renew/${id}`)
}
```

#### nginx.js - Nginx API
```javascript
export function getNginxStatus() {
  return axios.get('/api/nginx/status')
}

export function startNginx() {
  return axios.post('/api/nginx/start')
}

export function stopNginx() {
  return axios.post('/api/nginx/stop')
}
```

### 公共组件

#### 1. MonacoEditor.vue - 代码编辑器
**职责**：集成Monaco Editor编辑器

**功能**：
- 语法高亮
- 代码自动补全
- 错误提示
- 多语言支持

#### 2. FileManager.vue - 文件管理器
**职责**：文件和目录管理

**功能**：
- 文件树展示
- 文件上传下载
- 目录创建删除
- 文件预览编辑

#### 3. LogViewer.vue - 日志查看器
**职责**：日志文件查看和分析

**功能**：
- 分页加载
- 关键字搜索
- 日志级别过滤
- 实时刷新

### 状态管理 (stores/)

#### user.js - 用户状态
```javascript
export const useUserStore = defineStore('user', {
  state: () => ({
    token: localStorage.getItem('token') || '',
    userInfo: null
  }),
  
  getters: {
    isLoggedIn: (state) => !!state.token
  },
  
  actions: {
    async login(username, password) {
      const response = await axios.post('/api/user/login', { username, password })
      this.token = response.data.token
      this.userInfo = response.data.user
      localStorage.setItem('token', this.token)
    },
    
    logout() {
      this.token = ''
      this.userInfo = null
      localStorage.removeItem('token')
    }
  }
})
```

---

## 🗄️ 数据库模型详解

### 1. User - 用户表
```sql
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    email VARCHAR(100),
    role VARCHAR(20) DEFAULT 'user',  -- admin, user, viewer
    status INTEGER DEFAULT 1,           -- 1: active, 0: disabled
    last_login DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2. ConfigBackup - 配置备份表
```sql
CREATE TABLE config_backups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    backup_type VARCHAR(20),  -- auto, manual
    file_path VARCHAR(255),
    created_by INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (created_by) REFERENCES users(id)
);
```

### 3. AuditLog - 审计日志表
```sql
CREATE TABLE audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    action VARCHAR(50) NOT NULL,
    resource VARCHAR(100),
    details TEXT,
    ip_address VARCHAR(45),
    user_agent VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### 4. Certificate - SSL证书表
```sql
CREATE TABLE certificates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    domain VARCHAR(255) UNIQUE NOT NULL,
    cert_path VARCHAR(255) NOT NULL,
    key_path VARCHAR(255) NOT NULL,
    chain_path VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expire_at DATETIME NOT NULL,
    auto_renew BOOLEAN DEFAULT TRUE,
    status VARCHAR(20) DEFAULT 'active'
);
```

### 5. GitRepo - Git仓库表
```sql
CREATE TABLE git_repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    path VARCHAR(255) NOT NULL,
    remote_url VARCHAR(255),
    branch VARCHAR(50) DEFAULT 'main',
    last_sync DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 6. Statistics - 统计数据表
```sql
CREATE TABLE statistics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_type VARCHAR(50) NOT NULL,  -- page_view, bandwidth, request_time
    metric_value FLOAT NOT NULL,
    metric_label VARCHAR(100),
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## ⚙️ 配置管理

### config.yaml 配置项

```yaml
# 应用配置
app:
  title: "Nginx WebUI"
  version: "2.0.0"
  debug: false

# Nginx配置
nginx:
  bin: "/usr/sbin/nginx"
  conf: "/etc/nginx/nginx.conf"
  test_cmd: "/usr/sbin/nginx -t"

# 数据库配置
database:
  url: "sqlite:///./nginx_webui.db"
  echo: false

# 安全配置
security:
  secret_key: "your-secret-key-here"
  token_expire_minutes: 60
  password_min_length: 6

# Certbot配置
certbot:
  path: "/opt/certbot/certbot"
  email: "admin@example.com"
  webroot: "/var/www/html"
  auto_renew: true
  renew_before_days: 30

# 日志配置
logging:
  level: "INFO"
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "./logs/nginx_webui.log"

# Git配置
git:
  default_branch: "main"
  auto_commit: true
  commit_message: "Auto backup: {date}"

# 定时任务配置
cron:
  auto_backup: true
  backup_schedule: "0 2 * * *"  # 每天凌晨2点
  auto_renew_cert: true
  renew_schedule: "0 0 * * *"    # 每天凌晨
  log_rotation: true
  rotation_schedule: "0 0 * * 0"  # 每周日凌晨

# 备份配置
backup:
  max_backups: 30
  backup_path: "./backups"
  compress: true

# 监控配置
monitor:
  enabled: true
  interval: 30  # 秒
  alert_threshold:
    cpu: 80
    memory: 90
    disk: 85
```

### 环境变量覆盖

以下配置项可以通过环境变量覆盖：

```bash
# 数据库
export DATABASE_URL="postgresql://user:pass@localhost/nginx_webui"

# 安全
export SECRET_KEY="your-production-secret-key"
export TOKEN_EXPIRE_MINUTES=120

# Nginx
export NGINX_BIN="/usr/local/nginx/sbin/nginx"
export NGINX_CONF="/usr/local/nginx/conf/nginx.conf"

# Certbot
export CERTBOT_PATH="/usr/local/bin/certbot"
export LETSENCRYPT_EMAIL="ssl@example.com"
```

---

## 🚀 部署与运行

### 开发环境

#### 1. 后端启动
```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export DATABASE_URL="sqlite:///./nginx_webui.db"
export SECRET_KEY="dev-secret-key"

# 启动服务
uvicorn main:app --reload --host 0.0.0.0 --port 9000
```

#### 2. 前端启动
```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

访问 http://localhost:5173

### Docker部署

#### 1. 使用Docker Compose
```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f
```

#### 2. 构建Docker镜像
```bash
# 构建镜像
docker build -t nginx-webui:latest .

# 运行容器
docker run -d \
  --name nginx-webui \
  -p 9000:9000 \
  -v /path/to/nginx/conf:/etc/nginx \
  -v /path/to/backups:/app/backups \
  nginx-webui:latest
```

### 生产环境

#### 1. Nginx反向代理配置
```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:9000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

#### 2. HTTPS配置
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:9000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 默认账户

- **用户名**：admin
- **密码**：admin

⚠️ **重要**：首次登录后请立即修改默认密码！

### API文档

启动服务后访问：
- Swagger UI: http://localhost:9000/docs
- ReDoc: http://localhost:9000/redoc

---

## 📊 关键流程说明

### 1. 用户认证流程
```
用户登录 → 验证用户名密码 → 生成JWT Token → 返回Token
后续请求 → 携带Token → 验证Token → 处理请求
```

### 2. 证书申请流程
```
用户申请证书 → 验证域名所有权 → Certbot申请证书 
→ 保存证书文件 → 写入数据库 → 更新Nginx配置 → 重载Nginx
```

### 3. 配置保存流程
```
用户编辑配置 → 验证语法 → 保存到文件 → 创建备份 
→ 写入审计日志 → 重载Nginx → 返回结果
```

### 4. 自动备份流程
```
定时任务触发 → 读取Nginx配置 → 压缩文件 
→ 保存到备份目录 → 清理过期备份 → 记录日志
```

---

## 🛠️ 常见问题

### 1. Nginx无法启动
- 检查配置文件语法：`nginx -t`
- 查看错误日志：`tail -f /var/log/nginx/error.log`
- 确认端口未被占用：`netstat -tlnp | grep 80`

### 2. 证书申请失败
- 确认域名DNS解析正确
- 检查80端口是否开放
- 验证webroot目录权限
- 查看Certbot日志

### 3. 数据库连接失败
- 检查数据库文件权限
- 确认SQLite库已安装
- 验证数据库路径

### 4. 前端无法访问后端
- 检查CORS配置
- 确认后端服务运行
- 验证API路径配置

---

## 📚 相关资源

- [FastAPI文档](https://fastapi.tiangolo.com/)
- [Vue 3文档](https://vuejs.org/)
- [Element Plus文档](https://element-plus.org/)
- [Nginx文档](https://nginx.org/en/docs/)
- [Certbot文档](https://certbot.eff.org/)

---

**最后更新**：2026-05-13
**文档版本**：1.0.0
