#!/bin/bash

# 重启后端服务脚本

echo "正在停止旧的后端服务..."

# 停止占用端口 8000 的进程
PID=$(lsof -ti:8000 2>/dev/null)
if [ ! -z "$PID" ]; then
    echo "停止进程: $PID"
    kill -9 $PID 2>/dev/null
    sleep 2
fi

# 停止所有 uvicorn 进程（谨慎使用）
# pkill -f "uvicorn app.main:app" 2>/dev/null

echo "启动后端服务..."

cd "$(dirname "$0")/../backend"

# 检查依赖是否安装
if ! python3 -c "from jose import jwt; from email_validator import validate_email" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 初始化数据库
echo "初始化数据库..."
python3 -c "from app.database import init_db; init_db()" 2>&1 | grep -v "^$"

# 启动服务
echo "启动后端服务..."
echo "服务将在 http://127.0.0.1:8000 运行"
echo "API 文档: http://127.0.0.1:8000/docs"
echo "按 Ctrl+C 停止服务"
echo ""

python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

