"""
FastAPI 应用主入口
"""

from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, DB_PATH
from app.config import get_config
from app.routers import (
    auth,
    config,
    logs,
    files,
    audit,
    certificates,
    nginx_manager,
    users,
)
from app.routers import statistics, system

# 初始化数据库
init_db()

# 创建 FastAPI 应用
app = FastAPI(
    title="Nginx WebUI API", description="Nginx 管理系统的后端 API", version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由（必须在静态文件之前注册）
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(logs.router)
app.include_router(files.router)
app.include_router(audit.router)
app.include_router(certificates.router)
app.include_router(nginx_manager.router)
app.include_router(users.router)
app.include_router(statistics.router)
app.include_router(system.router)


@app.on_event("startup")
async def startup_event():
    """应用启动时打印核心配置信息"""
    cfg = get_config()
    print("\n" + "=" * 60)
    print("Nginx WebUI 核心配置路径")
    print("=" * 60)
    print(f"NGINX 配置目录:     {cfg.nginx.conf_dir}")
    print(f"Nginx 配置文件:     {cfg.nginx.config_path}")
    print(f"Nginx 可执行文件:   {cfg.nginx.executable}")
    print(f"静态文件目录:       {cfg.nginx.static_dir}")
    print(f"日志目录:           {cfg.nginx.log_dir}")
    print(f"SSL 证书目录:       {cfg.nginx.ssl_dir}")
    print(f"数据库文件:         {DB_PATH}")
    print(f"备份目录:           {cfg.backup.backup_dir}")
    print(f"Nginx 版本目录:     {cfg.nginx.versions_root}")
    print(f"Nginx 构建目录:     {cfg.nginx.build_root}")
    print(f"构建日志目录:       {cfg.nginx.build_logs_dir}")
    print(f"应用监听地址:       {cfg.app.host}:{cfg.app.port}")
    print("=" * 60 + "\n")

# 挂载静态文件目录（前端打包文件）
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    # 挂载静态资源目录（CSS、JS、图片等）
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # 提供前端静态文件服务（SPA 应用）
    # 注意：这个路由必须在最后注册，因为它会匹配所有路径
    @app.get("/{path:path}", include_in_schema=False)
    async def serve_frontend(path: str, request: Request):
        """提供前端静态文件服务，支持 SPA 路由"""
        # 安全检查：确保路径在 static_dir 内
        try:
            file_path = (static_dir / path).resolve()
            static_path = static_dir.resolve()
            if not str(file_path).startswith(str(static_path)):
                # 路径越界，返回 index.html
                path = "index.html"
        except Exception:
            path = "index.html"

        # 尝试返回请求的文件
        file_path = static_dir / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # 如果是目录或文件不存在，返回 index.html（SPA 路由支持）
        index_file = static_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file)

        return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.get("/", summary="API 根路径")
async def root():
    """API 根路径"""
    return {"message": "Nginx WebUI API", "version": "1.0.0", "docs": "/docs"}


@app.get("/api/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    config = get_config()
    return {"status": "ok", "config_loaded": config is not None}


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "服务器内部错误", "detail": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    config = get_config()
    # 调试模式下启用自动重载
    uvicorn.run(
        "app.main:app",
        host=config.app.host,
        port=config.app.port,
        reload=config.app.debug,  # 根据配置决定是否启用自动重载
    )
