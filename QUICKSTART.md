# 快速启动指南

## 默认账号信息

- **用户名**: `admin`
- **密码**: `admin`

## 启动步骤

### 1. 启动后端服务

在终端中运行：

```bash
cd backend
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

或者使用启动脚本：

```bash
bash scripts/start-backend.sh
```

后端服务将在 `http://127.0.0.1:8000` 启动。

### 2. 启动前端服务

在另一个终端中运行：

```bash
cd frontend
npm install  # 首次运行需要安装依赖
npm run dev
```

或者使用启动脚本：

```bash
bash scripts/start-frontend.sh
```

前端服务将在 `http://localhost:3001` 启动。

### 3. 访问系统

打开浏览器访问：`http://localhost:3001`

使用默认账号登录：
- 用户名: `admin`
- 密码: `admin`

## 常见问题

### 问题1: 后端无法启动

**错误**: `ModuleNotFoundError: No module named 'jose'`

**解决方案**:
```bash
cd backend
pip3 install -r requirements.txt
```

### 问题2: 前端无法启动

**错误**: `vite: command not found`

**解决方案**:
```bash
cd frontend
npm install
```

### 问题3: 登录失败

1. 确保后端服务正在运行（检查 `http://127.0.0.1:8000` 是否可访问）
2. 确保数据库已初始化（首次启动会自动初始化）
3. 检查浏览器控制台的错误信息

### 问题4: 数据库未初始化

手动初始化数据库：

```bash
cd backend
python3 -c "from app.database import init_db; init_db()"
```

## 使用 VSCode 调试

1. 按 `F5` 打开调试面板
2. 选择 "完整调试: 后端 + 前端" 配置
3. 点击运行按钮，同时启动后端和前端

## API 文档

后端启动后，访问以下地址查看 API 文档：

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

