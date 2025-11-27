# ==================== 第一阶段：构建前端 ====================
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/node:20.16 AS frontend-builder

# 设置工作目录
WORKDIR /app/frontend

# 仅复制依赖文件以利用缓存
COPY frontend/package*.json ./
RUN npm config set registry https://registry.npmmirror.com && npm install

# 复制剩余前端代码并构建
COPY frontend/ ./
RUN npm run build

# ==================== 第二阶段：运行后端 ====================
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/python:3.11.1

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV APP_PORT=8000

# 安装系统依赖（包含编译 Nginx 所需工具链）
RUN dnf update -y && \
    # 安装基础工具（基础镜像已包含 Python 和 pip）
    dnf install -y ca-certificates curl wget tar && \
    # 安装编译工具
    dnf install -y gcc gcc-c++ make && \
    # 安装开发库（编译 nginx 所需）
    dnf install -y pcre pcre-devel zlib zlib-devel openssl openssl-devel && \
    dnf clean all

# 设置工作目录
WORKDIR /app

# 复制后端代码
COPY backend/ /app/backend/

# 安装 Python 依赖
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/
RUN pip install --upgrade pip
RUN cd /app/backend && pip install --no-cache-dir -r requirements.txt

# 从第一阶段复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist/ /app/backend/static/

# 恢复工作目录
WORKDIR /app

# 创建必要的目录
RUN mkdir -p /app/backend/data/backups \
    && mkdir -p /app/backend/static \
    && mkdir -p /app/nginx/versions \
    && mkdir -p /app/nginx/build \
    && mkdir -p /app/nginx/build_logs

# 创建启动脚本（初始化数据库并启动 FastAPI）
RUN echo '#!/bin/bash' > /app/start.sh && \
    echo 'set -e' >> /app/start.sh && \
    echo '# 从环境变量读取端口，默认为 8000' >> /app/start.sh && \
    echo 'PORT=${APP_PORT:-8000}' >> /app/start.sh && \
    echo 'echo "初始化数据库..."' >> /app/start.sh && \
    echo 'cd /app/backend && python3 -c "from app.database import init_db; init_db()"' >> /app/start.sh && \
    echo 'echo "启动 FastAPI 服务在端口 $PORT..."' >> /app/start.sh && \
    echo 'cd /app/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT' >> /app/start.sh && \
    chmod +x /app/start.sh

# 暴露端口
EXPOSE 8000

# 启动服务（直接启动 Python/FastAPI）
CMD ["/app/start.sh"]

