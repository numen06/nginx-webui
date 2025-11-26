#!/bin/bash

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Nginx WebUI 打包脚本"
echo "=========================================="

# 获取版本号
VERSION=${1:-"latest"}
if [ "$VERSION" != "latest" ] && [[ ! "$VERSION" =~ ^v ]]; then
    VERSION="v${VERSION}"
fi

echo "版本: $VERSION"
echo "构建时间: $(date '+%Y-%m-%d %H:%M:%S')"

# 清理旧的构建产物
echo ""
echo "清理旧的构建产物..."
rm -rf "$PROJECT_DIR/frontend/dist"
rm -rf "$PROJECT_DIR/.dockerignore"

# 构建前端
echo ""
echo "步骤 1/4: 构建前端..."
bash "$SCRIPT_DIR/build.sh"

# 验证后端依赖
echo ""
echo "步骤 2/4: 检查后端依赖..."
cd "$PROJECT_DIR/backend"
if [ ! -f "requirements.txt" ]; then
    echo "错误: requirements.txt 不存在"
    exit 1
fi

# 创建 .dockerignore
echo ""
echo "步骤 3/4: 创建 .dockerignore..."
cat > "$PROJECT_DIR/.dockerignore" <<EOF
.git
.gitignore
README.md
node_modules
frontend/node_modules
frontend/dist
*.log
.DS_Store
.vscode
.idea
__pycache__
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info
dist
build
.env
.env.local
EOF

# 构建 Docker 镜像
echo ""
echo "步骤 4/4: 构建 Docker 镜像..."
cd "$PROJECT_DIR"

IMAGE_NAME="nginx-webui"
IMAGE_TAG="${IMAGE_NAME}:${VERSION}"
IMAGE_LATEST="${IMAGE_NAME}:latest"

docker build -t "$IMAGE_TAG" -t "$IMAGE_LATEST" .

echo ""
echo "=========================================="
echo "构建完成！"
echo "=========================================="
echo "镜像标签:"
echo "  - $IMAGE_TAG"
echo "  - $IMAGE_LATEST"
echo ""
echo "运行容器:"
echo "  docker run -d -p 80:80 --name nginx-webui $IMAGE_LATEST"
echo ""
echo "或使用 docker-compose:"
echo "  docker-compose up -d"
echo "=========================================="

