# 修复后端连接问题

## 当前问题

前端无法连接到后端服务（`ETIMEDOUT 127.0.0.1:8000`）。

## 快速修复步骤

### 方法 1：使用重启脚本（推荐）

```bash
bash scripts/restart-backend.sh
```

### 方法 2：手动重启

#### 步骤 1：停止旧进程

```bash
# 查找并停止占用 8000 端口的进程
lsof -ti:8000 | xargs kill -9

# 或者停止所有 uvicorn 进程
pkill -f "uvicorn app.main:app"
```

#### 步骤 2：确认端口已释放

```bash
lsof -ti:8000
# 如果没有任何输出，说明端口已释放
```

#### 步骤 3：启动后端服务

```bash
cd backend
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 方法 3：使用 VSCode 调试

1. **停止当前调试会话**
   - 在 VSCode 调试面板点击停止按钮
   - 或者按 `Shift + F5`

2. **重新启动调试**
   - 按 `F5`
   - 选择 "Python: FastAPI (后端)" 配置
   - 等待服务启动

## 验证后端服务

后端服务正常启动后，你应该看到：

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [PID] using WatchFiles
INFO:     Started server process [PID]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

### 测试连接

在另一个终端运行：

```bash
# 测试健康检查
curl http://127.0.0.1:8000/api/health

# 应该返回：
# {"status":"ok","config_loaded":true}

# 测试根路径
curl http://127.0.0.1:8000/

# 测试 API 文档
# 在浏览器中打开: http://127.0.0.1:8000/docs
```

## 常见问题

### 问题 1：端口仍被占用

如果端口仍被占用，查找进程：

```bash
# 查看占用端口的进程详情
lsof -i:8000

# 强制停止
kill -9 $(lsof -ti:8000)
```

### 问题 2：导入错误

如果看到模块导入错误：

```bash
cd backend
pip3 install -r requirements.txt
```

### 问题 3：数据库错误

如果看到数据库错误：

```bash
cd backend
python3 -c "from app.database import init_db; init_db()"
```

## 检查清单

- [ ] 端口 8000 未被占用
- [ ] 所有 Python 依赖已安装
- [ ] 数据库已初始化
- [ ] 后端服务正常启动（看到 "Application startup complete"）
- [ ] curl 测试可以连接
- [ ] 前端代理配置正确

## 启动后检查

1. **后端服务日志** - 查看是否有错误信息
2. **浏览器控制台** - 查看前端错误信息
3. **网络请求** - 在浏览器开发者工具的 Network 标签查看 API 请求状态

