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
├── frontend/         # Vue 前端
├── nginx/            # Nginx 配置文件
├── scripts/          # 构建和启动脚本
├── docker-compose.yml
├── Dockerfile
└── README.md
```

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

## 默认账户

- 用户名: `admin`
- 密码: `admin`

**首次登录后请立即修改密码！**

## 许可证

MIT License

