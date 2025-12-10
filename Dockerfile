# ==================== 第一阶段：构建前端 ====================
FROM alibaba-cloud-linux-3-registry.cn-hangzhou.cr.aliyuncs.com/alinux3/node:20.16 AS frontend-builder

# 设置工作目录并确保权限
WORKDIR /app/frontend
RUN mkdir -p /app/frontend && chown -R node:node /app/frontend
USER node

# 仅复制依赖文件以利用缓存
COPY --chown=node:node frontend/package*.json ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm install && \
    npm cache clean --force

# 复制剩余前端代码并构建
COPY --chown=node:node frontend/ ./
RUN npm run build && \
    rm -rf node_modules && \
    rm -rf /tmp/* /home/node/.npm /home/node/.cache

# ==================== 第二阶段：运行后端 ====================
FROM ac2-registry.cn-hangzhou.cr.aliyuncs.com/ac2/base:alinux3.2104-py312

# 设置环境变量
ENV PYTHONUNBUFFERED=1
ENV APP_PORT=8000

#设置时区
RUN ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime

RUN curl -o /etc/yum.repos.d/alinux3.repo https://mirrors.aliyun.com/alinux/3.2104/os/x86_64/alinux3.repo

# 安装系统依赖（包含编译 Nginx 所需工具链）
# 说明：
# - 阿里云龙蜥镜像在某些环境下 RPM 数据库可能是 bdb_ro，只读导致 dnf 事务失败
# - 这里先尽量修复 RPM 数据库，再用 dnf 安装，避免 update 带来额外风险
RUN set -eux; \
    # 修复 RPM 数据库，忽略错误（在只读场景下尽可能不影响后续）
    rm -f /var/lib/rpm/__db* || true; \
    rpm --rebuilddb || true; \
    # 只安装必要包，不执行 dnf update 以减少事务复杂度
    dnf install -y \
        ca-certificates \
        curl wget tar \
        iproute iputils net-tools \
        gcc gcc-c++ make \
        pcre pcre-devel \
        zlib zlib-devel \
        openssl openssl-devel && \
    dnf clean all && \
    rm -rf /var/cache/dnf/* /tmp/* /var/tmp/*


# 设置工作目录
WORKDIR /app

# 复制后端代码（排除不需要的文件，.dockerignore 已处理）
COPY backend/ /app/backend/

# 清理可能存在的缓存文件
RUN find /app/backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /app/backend -type f -name "*.pyc" -delete 2>/dev/null || true && \
    find /app/backend -type f -name "*.pyo" -delete 2>/dev/null || true

# 安装 Python 依赖（合并命令减少层数）
RUN pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/ && \
    pip install --upgrade pip && \
    cd /app/backend && pip install --no-cache-dir -r requirements.txt

# 准备数据目录结构，便于通过 /app/data 单目录持久化
# 同时清理临时文件和缓存
# 记录构建时间作为系统版本
RUN BUILD_TIME=$(date +%Y%m%d%H%M%S) && \
    mkdir -p /app/data/backend \
    && mkdir -p /app/data/logs \
    && mkdir -p /app/data/ssl \
    && mkdir -p /app/data/nginx/versions \
    && mkdir -p /app/data/nginx/build_logs \
    && mkdir -p /app/nginx \
    && echo "$BUILD_TIME" > /app/data/backend/.build_time \
    && rm -rf /app/backend/data && ln -s /app/data/backend /app/backend/data \
    && rm -rf /var/log/nginx && ln -s /app/data/logs /var/log/nginx \
    && rm -rf /app/nginx/ssl && ln -s /app/data/ssl /app/nginx/ssl \
    && rm -rf /app/nginx/versions && ln -s /app/data/nginx/versions /app/nginx/versions \
    && rm -rf /app/nginx/build_logs && ln -s /app/data/nginx/build_logs /app/nginx/build_logs \
    && rm -rf /tmp/* /var/tmp/* \
    && find /app/backend -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true \
    && find /app/backend -type f -name "*.pyc" -delete 2>/dev/null || true

# 从第一阶段复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist/ /app/backend/static/

# 恢复工作目录
WORKDIR /app

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

