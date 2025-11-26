#!/bin/bash

set -e

echo "开始构建前端..."

# 进入前端目录
cd "$(dirname "$0")/../frontend"

# 检查 node_modules 是否存在
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm install
fi

# 构建前端
echo "构建前端项目..."
npm run build

# 检查构建产物
if [ ! -d "dist" ]; then
    echo "错误: 前端构建失败，dist 目录不存在"
    exit 1
fi

echo "前端构建完成！"
echo "构建产物位于: frontend/dist/"

