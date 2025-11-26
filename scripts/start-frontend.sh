#!/bin/bash

# 启动前端服务脚本

cd "$(dirname "$0")/../frontend"

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "正在安装前端依赖..."
    npm install
fi

# 启动开发服务器
echo "启动前端开发服务器..."
npm run dev

