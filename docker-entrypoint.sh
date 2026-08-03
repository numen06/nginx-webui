#!/bin/bash
set -e

PORT=${APP_PORT:-8000}
CERTBOT_CONFIG_DIR=${CERTBOT_CONFIG_DIR:-/app/data/letsencrypt}
mkdir -p "$CERTBOT_CONFIG_DIR"

# 兼容旧容器：先迁移 Certbot 数据，再切换为持久化软链接。
if [ -d /etc/letsencrypt ] && [ ! -L /etc/letsencrypt ]; then
  if [ -z "$(ls -A "$CERTBOT_CONFIG_DIR" 2>/dev/null)" ] && [ -n "$(ls -A /etc/letsencrypt 2>/dev/null)" ]; then
    echo "检测到旧版 /etc/letsencrypt，正在迁移到 $CERTBOT_CONFIG_DIR ..."
    cp -a /etc/letsencrypt/. "$CERTBOT_CONFIG_DIR"/ || true
  fi
  rm -rf /etc/letsencrypt
fi
if [ ! -e /etc/letsencrypt ]; then ln -s "$CERTBOT_CONFIG_DIR" /etc/letsencrypt; fi
if [ -L /etc/letsencrypt ]; then echo "Certbot 数据目录: $(readlink -f /etc/letsencrypt)"; fi

# 优先恢复已持久化的 Nginx，避免 WebUI/数据库初始化期间反向代理中断。
NGINX_HOME=/app/data/nginx/versions/last
NGINX_BIN="$NGINX_HOME/sbin/nginx"
NGINX_CONF="$NGINX_HOME/conf/nginx.conf"
if [ -x "$NGINX_BIN" ] && [ -f "$NGINX_CONF" ]; then
  if "$NGINX_BIN" -t -c "$NGINX_CONF" -p "$NGINX_HOME"; then
    "$NGINX_BIN" -c "$NGINX_CONF" -p "$NGINX_HOME" || echo "警告: Nginx 提前启动失败，继续启动 WebUI"
  else
    echo "警告: Nginx 配置校验失败，继续启动 WebUI"
  fi
fi

echo "启动 FastAPI 服务在端口 $PORT..."
cd /app/backend
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
