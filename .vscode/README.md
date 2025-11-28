# VSCode 调试配置说明

## 调试配置

本项目的 VSCode 调试配置包含以下选项：

### 后端调试

1. **Python: FastAPI (后端)** - 启动完整的 FastAPI 开发服务器并附加调试器
2. **Python: FastAPI (当前文件)** - 调试当前打开的 Python 文件
3. **Python: 调试测试** - 运行并调试 pytest 测试

### 前端调试

1. **Vue: 前端开发服务器** - 启动 Vite 开发服务器
2. **Chrome: 调试前端** - 在 Chrome 中调试前端应用（需要先启动开发服务器）
3. **Attach to Chrome** - 附加到已运行的 Chrome 实例

### 复合调试

- **完整调试: 后端 + 前端** - 同时启动后端和前端开发服务器进行调试

## 使用方法

1. 按 `F5` 或点击调试面板
2. 选择相应的调试配置
3. 设置断点
4. 开始调试

## 前置条件

### 后端调试
- 安装 Python 扩展：`ms-python.python`
- 安装 Python 依赖：`pip3 install -r backend/requirements.txt`

### 前端调试
- 安装 Volar 扩展：`Vue.volar`
- 安装前端依赖：`cd frontend && npm install`

## 任务（Tasks）

可以通过 `Ctrl+Shift+P` 运行任务：
- `npm: dev (frontend)` - 启动前端开发服务器
- `Python: 启动后端` - 启动后端服务器
- `初始化数据库` - 初始化 SQLite 数据库
- `安装后端依赖` - 安装 Python 依赖
- `安装前端依赖` - 安装 Node.js 依赖
- `构建前端` - 构建前端生产版本

