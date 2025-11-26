#!/bin/bash

# 启动后端服务脚本

cd "$(dirname "$0")/../backend"

# 检查依赖是否安装
if ! python3 -c "from jose import jwt" 2>/dev/null; then
    echo "正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 初始化数据库
echo "初始化数据库..."
python3 -c "from app.database import init_db; init_db()"

# 启动服务
# 检查是否启用调试模式（默认启用）
DEBUG_MODE=${DEBUG:-true}
RELOAD_FLAG=""
if [ "$DEBUG_MODE" = "true" ] || [ "$DEBUG_MODE" = "1" ]; then
    RELOAD_FLAG="--reload"
    echo "启动后端服务（调试模式，自动重载已启用）..."
else
    echo "启动后端服务（生产模式）..."
fi

python3 -m uvicorn app.main:app $RELOAD_FLAG --host 127.0.0.1 --port 8000

