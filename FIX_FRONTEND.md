# 修复前端端口冲突问题

## 问题描述

端口 3000 被多个项目占用，导致前端服务冲突。

## 解决方案

### 已更改的配置

1. **前端端口改为 3001** - 避免与 `feige-gateway` 项目冲突
2. **主机绑定为 127.0.0.1** - 更安全的本地访问

### 启动前端服务

#### 方法 1：使用清理脚本（推荐）

```bash
bash scripts/clean-frontend.sh
```

#### 方法 2：手动启动

```bash
cd frontend
npm run dev
```

### 访问地址

前端服务现在运行在：
- **http://localhost:3001**

### 验证

启动后，你应该看到：

```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:3001/
  ➜  Network: use --host to expose
```

### 如果仍然看到其他项目

1. **清理浏览器缓存**
   - 按 `Ctrl+Shift+R` (Windows/Linux) 或 `Cmd+Shift+R` (Mac) 强制刷新
   - 或清除浏览器缓存

2. **检查 URL**
   - 确保访问的是 `http://localhost:3001` 而不是 `http://localhost:3000`

3. **停止所有冲突服务**
   ```bash
   # 停止所有占用 3000 和 3001 端口的进程
   lsof -ti:3000 | xargs kill -9
   lsof -ti:3001 | xargs kill -9
   ```

4. **使用无痕模式**
   - 打开浏览器的无痕/隐私模式
   - 访问 `http://localhost:3001`

## 端口配置说明

- **前端**: `3001` (已更改)
- **后端**: `8000` (保持不变)

如果需要更改端口，修改 `frontend/vite.config.js` 中的 `port` 配置。

