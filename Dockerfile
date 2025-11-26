# 使用阿里云的 Python 3.11 轻量级镜像作为基础
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/python:3.11.1

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 安装系统依赖（包含编译 Nginx 所需工具链）
RUN dnf update -y && \
    dnf install -y \
    nginx \
    python3 \
    python3-pip \
    certbot \
    openssl \
    supervisor \
    curl \
    gcc \
    gcc-c++ \
    make \
    pcre \
    pcre-devel \
    zlib \
    zlib-devel \
    openssl-devel \
    ca-certificates \
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

# 复制 Nginx 配置
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY nginx/conf.d/ /etc/nginx/conf.d/

# 创建必要的目录（包括多版本 Nginx 相关目录）
RUN mkdir -p /app/backend/data/backups \
    && mkdir -p /app/backend/static \
    && mkdir -p /etc/nginx/ssl \
    && mkdir -p /var/log/nginx \
    && mkdir -p /var/run \
    && mkdir -p /app/nginx/versions \
    && mkdir -p /app/nginx/build \
    && mkdir -p /app/nginx/build_logs

# 复制启动脚本
COPY scripts/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# 创建启动脚本（初始化数据库并测试 nginx 配置）
RUN echo '#!/bin/bash' > /app/init.sh && \
    echo 'set -e' >> /app/init.sh && \
    echo 'echo "初始化数据库..."' >> /app/init.sh && \
    echo 'cd /app/backend && python3 -c "from app.database import init_db; init_db()"' >> /app/init.sh && \
    echo 'echo "测试 Nginx 配置..."' >> /app/init.sh && \
    echo '/usr/sbin/nginx -t' >> /app/init.sh && \
    echo 'echo "初始化完成"' >> /app/init.sh && \
    chmod +x /app/init.sh

# 创建 Supervisor 配置
RUN mkdir -p /etc/supervisor/conf.d && \
    echo '[supervisord]' > /etc/supervisor/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisor/supervisord.conf && \
    echo '' >> /etc/supervisor/supervisord.conf && \
    echo '[include]' >> /etc/supervisor/supervisord.conf && \
    echo 'files = /etc/supervisor/conf.d/*.conf' >> /etc/supervisor/supervisord.conf && \
    echo '' > /etc/supervisor/conf.d/init.conf && \
    echo '[program:init]' >> /etc/supervisor/conf.d/init.conf && \
    echo 'command=/app/init.sh' >> /etc/supervisor/conf.d/init.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/init.conf && \
    echo 'autorestart=false' >> /etc/supervisor/conf.d/init.conf && \
    echo 'startretries=1' >> /etc/supervisor/conf.d/init.conf && \
    echo 'stdout_logfile=/var/log/init.log' >> /etc/supervisor/conf.d/init.conf && \
    echo 'stderr_logfile=/var/log/init.log' >> /etc/supervisor/conf.d/init.conf && \
    echo '' > /etc/supervisor/conf.d/nginx.conf && \
    echo '[program:nginx]' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'command=/usr/sbin/nginx -g "daemon off;"' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'priority=10' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'startsecs=2' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'startretries=3' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'stdout_logfile=/var/log/nginx/nginx_stdout.log' >> /etc/supervisor/conf.d/nginx.conf && \
    echo 'stderr_logfile=/var/log/nginx/nginx_stderr.log' >> /etc/supervisor/conf.d/nginx.conf && \
    echo '' > /etc/supervisor/conf.d/fastapi.conf && \
    echo '[program:fastapi]' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'command=cd /app/backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'priority=20' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'startsecs=5' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'startretries=3' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'stdout_logfile=/var/log/fastapi_stdout.log' >> /etc/supervisor/conf.d/fastapi.conf && \
    echo 'stderr_logfile=/var/log/fastapi_stderr.log' >> /etc/supervisor/conf.d/fastapi.conf

# 暴露端口
EXPOSE 80 443

# 启动服务（使用 supervisor 管理 nginx 和 fastapi）
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]

