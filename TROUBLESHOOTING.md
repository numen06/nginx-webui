# 故障排除指南

## 问题：请求失败 / 无法连接到后端

### 症状
- 前端显示"请求失败"
- 浏览器控制台显示网络错误
- curl 测试无法连接到后端

### 解决方法

#### 1. 检查后端服务是否正在运行

```bash
# 检查端口是否被占用
lsof -ti:8000

# 或者检查进程
ps aux | grep uvicorn
```

#### 2. 确认后端服务正常启动

后端服务应该输出类似以下信息：
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

#### 3. 测试后端 API

```bash
# 测试健康检查
curl http://127.0.0.1:8000/api/health

# 测试根路径
curl http://127.0.0.1:8000/
```

#### 4. 检查依赖是否完整安装

```bash
cd backend
pip3 install -r requirements.txt
```

#### 5. 手动启动后端服务

```bash
cd backend
python3 -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

#### 6. 检查常见错误

##### 错误：ModuleNotFoundError

如果看到缺少模块的错误，安装缺失的依赖：

```bash
pip3 install <缺失的模块名>
```

##### 错误：Address already in use

端口被占用，可以：
- 杀死占用端口的进程：`kill $(lsof -ti:8000)`
- 或者更改端口配置

##### 错误：数据库初始化失败

手动初始化数据库：

```bash
cd backend
python3 -c "from app.database import init_db; init_db()"
```

## 问题：登录失败

### 症状
- 输入 admin/admin 后提示"用户名或密码错误"
- 前端显示登录失败

### 解决方法

#### 1. 检查数据库和用户

```bash
cd backend
python3 -c "
from app.database import SessionLocal
from app.models import User
db = SessionLocal()
user = db.query(User).filter(User.username == 'admin').first()
print(f'用户存在: {user is not None}')
if user:
    print(f'用户状态: {\"激活\" if user.is_active else \"禁用\"}')
db.close()
"
```

#### 2. 重新初始化数据库（会删除所有数据）

```bash
cd backend
python3 -c "from app.database import reset_db; reset_db()"
```

#### 3. 检查后端日志

查看后端终端输出的错误信息

## 问题：前端无法启动

### 症状
- `npm run dev` 报错
- `vite: command not found`

### 解决方法

```bash
cd frontend
# 删除 node_modules 和重新安装
rm -rf node_modules package-lock.json
npm install
npm run dev
```

## 问题：API 代理不工作

### 症状
- 前端请求显示 404 或连接失败
- 浏览器控制台显示 CORS 错误

### 解决方法

#### 1. 检查 Vite 代理配置

确保 `frontend/vite.config.js` 中的代理配置正确：

```javascript
proxy: {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true
  }
}
```

#### 2. 检查后端 CORS 配置

后端应该允许所有来源（开发环境）：

```python
allow_origins=["*"]
```

#### 3. 重启前端服务

更改代理配置后需要重启前端服务。

## 调试技巧

### 查看后端日志

后端服务会在终端输出详细的日志，包括：
- 请求路径
- 请求方法
- 响应状态码
- 错误堆栈

### 查看浏览器控制台

打开浏览器开发者工具（F12），查看：
- Console 标签：JavaScript 错误和日志
- Network 标签：API 请求和响应

### 使用 API 文档

后端启动后，访问 `http://127.0.0.1:8000/docs` 查看 Swagger UI，可以直接测试 API。

### 测试数据库连接

```bash
cd backend
python3 -c "from app.database import SessionLocal; db = SessionLocal(); print('数据库连接成功'); db.close()"
```

## 获取帮助

如果以上方法都无法解决问题，请：

1. 检查所有终端的错误输出
2. 查看浏览器控制台的完整错误信息
3. 检查系统日志
4. 提供完整的错误堆栈信息

