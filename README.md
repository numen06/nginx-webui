# Nginx WebUI

一个基于 FastAPI 和 Vue 3 的 Nginx 管理 Web 界面，提供配置管理、日志查看、文件管理、证书管理等功能。

## 功能特性

- ✅ Nginx 配置管理（编辑、测试、重载）
- ✅ 配置备份和恢复（保留最近 10 个备份）
- ✅ 日志查看（访问日志、错误日志）
- ✅ 静态文件管理（上传、编辑、删除）
- ✅ 证书管理（Certbot 自动申请、手动上传）
- ✅ 操作日志记录（审计功能）
- ✅ 基础认证（JWT Token）
- ✅ Docker 容器化部署
- ✅ Git 仓库同步（配置凭据后，一键推送当前 Nginx 配置）

## 技术栈

### 后端
- FastAPI
- SQLAlchemy (SQLite)
- Pydantic
- Certbot

### 前端
- Vue 3 + Composition API
- Vite
- Element Plus
- Monaco Editor

## 项目结构

```
nginx-webui/
├── backend/          # FastAPI 后端
│   └── app/          # 应用代码
├── frontend/         # Vue 前端
├── nginx/            # Nginx 默认配置文件（与 app 同级）
│   ├── nginx.conf    # 主配置文件
│   └── conf.d/       # 配置文件目录
├── data/             # 动态数据目录（运行时生成）
│   ├── logs/         # 日志文件
│   ├── ssl/          # SSL 证书
│   ├── backups/      # 配置备份
│   └── nginx/        # Nginx 多版本管理数据
│       ├── versions/ # 下载编译的 Nginx 版本
│       ├── build/    # 编译临时目录
│       └── build_logs/ # 编译日志
├── scripts/          # 构建和启动脚本
├── docker-compose.yml
├── Dockerfile
└── README.md
```

### 目录说明

- **nginx/**：存放 Nginx 的默认配置文件（nginx.conf、conf.d 等），这些是程序的默认配置
- **data/**：存放所有动态生成和下载的数据，包括：
  - 日志文件（logs/）
  - SSL 证书（ssl/）
  - 配置备份（backups/）
  - 下载编译的 Nginx 版本（nginx/versions/）
  - 编译临时文件和日志（nginx/build/、nginx/build_logs/）

## 快速开始

### 开发环境

#### 后端开发

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

#### 前端开发

```bash
cd frontend
npm install
npm run dev
```

### Docker 部署

#### 构建镜像

```bash
bash scripts/package.sh
```

#### 运行容器

```bash
docker-compose up -d
```

或使用 Docker 命令：

```bash
docker run -d \
  -p 80:80 \
  -v $(pwd)/data:/app/backend/data \
  --name nginx-webui \
  nginx-webui:latest
```

## 配置说明

配置文件位于 `backend/config.yaml`，可以配置：

- Nginx 相关路径
- 应用端口和主机
- 备份策略
- SSL 证书路径

也可以通过环境变量覆盖配置。

## Git 配置同步

1. 登录前端，进入左侧菜单的 **Git 配置同步** 页面并填写：
   - 项目名称（决定 `data/git/<项目名称>/` 目录，默认建议为当前根目录名）
   - 仓库地址（建议 HTTPS）
   - 目标分支（默认 `main`）
   - 账号与密码（凭证只保存在后端数据库，不会回显）
2. 保存后即可点击「立即同步」，系统会：
   - 以填写的项目名称（若未填写则使用默认值）组织本地仓库
   - 将正在使用的 `nginx.conf` 导出到 `data/git/<项目名称>/` 目录
   - 自动执行 `git add/commit/push` 推送到远端
3. 同步状态（成功/失败/无变更）会显示在卡片中，并记录最近一次的时间与消息。

> 注意：首次同步会在 `data/git` 下克隆仓库，请确保容器或宿主机具备访问目标 Git 服务的网络权限。

## 默认账户

- 用户名: `admin`
- 密码: `admin`

**首次登录后请立即修改密码！**

## 许可证

MIT License

