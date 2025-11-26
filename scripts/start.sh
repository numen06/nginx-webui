#!/bin/bash

# 初始化数据库
cd /app/backend
python3 -c "from app.database import init_db; init_db()"

# 启动 Nginx（后台）
nginx

# 启动 FastAPI
cd /app/backend
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

