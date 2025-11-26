"""
FastAPI 应用主入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
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
    statistics,
)

# 初始化数据库
init_db()

# 创建 FastAPI 应用
app = FastAPI(
    title="Nginx WebUI API",
    description="Nginx 管理系统的后端 API",
    version="1.0.0"
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router)
app.include_router(config.router)
app.include_router(logs.router)
app.include_router(files.router)
app.include_router(audit.router)
app.include_router(certificates.router)
app.include_router(nginx_manager.router)
app.include_router(users.router)
app.include_router(statistics.router)


@app.get("/", summary="API 根路径")
async def root():
    """API 根路径"""
    return {
        "message": "Nginx WebUI API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    config = get_config()
    return {
        "status": "ok",
        "config_loaded": config is not None
    }


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "服务器内部错误",
            "detail": str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    config = get_config()
    # 调试模式下启用自动重载
    uvicorn.run(
        "app.main:app",
        host=config.app.host,
        port=config.app.port,
        reload=config.app.debug  # 根据配置决定是否启用自动重载
    )

