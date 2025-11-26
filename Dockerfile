# 使用阿里云的 Python 3.11 轻量级镜像作为基础
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/python:3.11.1

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 安装系统依赖（包含编译 Nginx 所需工具链）
RUN dnf update -y && \
    dnf install -y \
    python3 \
    python3-pip \
    ca-certificates \
    curl \
    gcc \
    gcc-c++ \
    make \
    pcre \
    pcre-devel \
    zlib \
    zlib-devel \
    openssl \
    openssl-devel \
    wget \
    tar \
    && dnf clean all

# 设置工作目录
WORKDIR /app

# 复制后端代码
COPY backend/ /app/backend/

# 安装 Python 依赖
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
 cd /app/backend && pip3 install --no-cache-dir -r requirements.txt

# 复制前端打包文件到后端目录（通过 Python/FastAPI 提供静态文件服务）
COPY frontend/dist/ /app/backend/static/

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
    echo 'echo "初始化数据库..."' >> /app/start.sh && \
    echo 'cd /app/backend && python3 -c "from app.database import init_db; init_db()"' >> /app/start.sh && \
    echo 'echo "启动 FastAPI 服务..."' >> /app/start.sh && \
    echo 'cd /app/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000' >> /app/start.sh && \
    chmod +x /app/start.sh

# 暴露端口
EXPOSE 8000

# 启动服务（直接启动 Python/FastAPI）
CMD ["/app/start.sh"]

