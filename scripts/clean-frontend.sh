#!/bin/bash

# 清理并重启前端服务

echo "正在清理前端服务..."

# 停止占用端口 3000 的进程
PIDS=$(lsof -ti:3000 2>/dev/null)
if [ ! -z "$PIDS" ]; then
    echo "停止占用端口 3000 的进程: $PIDS"
    echo "$PIDS" | xargs kill -9 2>/dev/null
    sleep 2
fi

# 停止所有 vite 进程（谨慎使用）
# pkill -f "vite" 2>/dev/null

echo "端口 3000 已清理"

# 检查是否在正确的目录
if [ ! -f "package.json" ]; then
    cd "$(dirname "$0")/../frontend"
fi

echo "当前目录: $(pwd)"
echo "项目名称: $(grep -E '"name"' package.json | cut -d'"' -f4)"

# 检查 node_modules
if [ ! -d "node_modules" ]; then
    echo "正在安装依赖..."
    npm install
fi

echo ""
echo "启动前端开发服务器..."
echo "服务将在 http://localhost:3000 运行"
echo "按 Ctrl+C 停止服务"
echo ""

npm run dev

