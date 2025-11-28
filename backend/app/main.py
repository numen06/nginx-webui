"""
FastAPI 应用主入口
"""

import shutil
import threading
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import init_db, DB_PATH
from app.config import get_config
from app.utils.nginx import is_nginx_available
from app.utils.nginx_versions import get_active_version
from app.routers.nginx_manager import (
    _list_all_versions,
    _start_nginx_version_internal,
    _get_last_started_version,
    _get_install_path,
    _get_nginx_executable,
    _get_default_nginx_tar_path,
    _get_build_root,
    _compile_nginx_from_source,
)
from app.routers import (
    auth,
    config,
    logs,
    files,
    audit,
    certificates,
    nginx_manager,
    users,
    git,
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
app.include_router(git.router)
app.include_router(statistics.router)
app.include_router(system.router)


@app.on_event("startup")
async def startup_event():
    """应用启动时打印核心配置信息并自动启动nginx"""
    cfg = get_config()
    nginx_available = is_nginx_available()
    
    print("\n" + "=" * 60)
    print("Nginx WebUI 核心配置路径")
    print("=" * 60)
    # 尝试获取活动版本的配置路径
    try:
        from app.utils.nginx import get_config_path
        from app.utils.nginx_versions import get_active_version
        config_path = get_config_path()
        active = get_active_version()
        if active:
            print(f"Nginx 活动版本:     {active['version']}")
            print(f"Nginx 安装路径:     {active['install_path']}")
            print(f"Nginx 配置文件:     {config_path}")
            print(f"Nginx 配置目录:     {active['install_path'] / 'conf' / 'conf.d'}")
        else:
            print(f"Nginx 配置文件:     {config_path}")
            print(f"注意: 未找到活动版本，配置文件路径为备用路径")
    except FileNotFoundError:
        print(f"Nginx 配置文件:     未找到（需要先下载并编译一个 Nginx 版本）")
        print(f"备用配置路径:       {cfg.nginx.config_path} (已弃用)")
    print(f"Nginx 可执行文件:   {cfg.nginx.executable}")
    print(f"Nginx 状态:         {'✓ 可用' if nginx_available else '✗ 未安装或不可用'}")
    if not nginx_available:
        print(f"                   提示: 程序可以正常运行，但需要 Nginx 才能使用相关功能")
        print(f"                   安装 Nginx 后，可通过配置文件指定 nginx.executable 路径")
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
    
    # 自动启动nginx（如果有已安装的版本）
    try:
        # 检查是否有运行中的nginx
        active = get_active_version()
        if active is not None:
            print(f"✓ Nginx 版本 {active['version']} 已在运行")
        else:
            version_to_start = None
            
            # 1. 优先尝试启动最后执行的nginx版本
            last_started = _get_last_started_version()
            if last_started:
                install_path = _get_install_path(last_started)
                executable = _get_nginx_executable(install_path)
                if install_path.exists() and executable.exists():
                    version_to_start = last_started
                    print(f"检测到最后执行的 Nginx 版本: {last_started}")
            
            # 2. 如果没有最后执行的版本或该版本不存在，尝试启动发布版（last目录）
            if version_to_start is None:
                last_install_path = _get_install_path("last")
                last_executable = _get_nginx_executable(last_install_path)
                if last_install_path.exists() and last_executable.exists():
                    version_to_start = "last"
                    print("检测到发布版 Nginx (last目录)")
            
            # 3. 如果都没有，则启动最新版本（保持原有逻辑）
            if version_to_start is None:
                all_versions = _list_all_versions()
                compiled_versions = [v for v in all_versions if v.compiled]
                
                if compiled_versions:
                    # 按版本号排序，优先启动最新版本
                    compiled_versions.sort(key=lambda x: x.version, reverse=True)
                    latest_version = compiled_versions[0]
                    version_to_start = latest_version.version
                    print(f"未找到最后执行的版本或发布版，将启动最新版本: {version_to_start}")
            
            # 启动选定的版本
            if version_to_start:
                print(f"正在自动启动 Nginx 版本 {version_to_start}...")
                result = _start_nginx_version_internal(version_to_start)
                
                if result["success"]:
                    print(f"✓ {result['message']}")
                else:
                    print(f"✗ 自动启动失败: {result['message']}")
            else:
                # 4. 如果都没有，尝试使用默认nginx压缩包自动编译（后台运行）
                default_version = "1.29.3"
                default_tar = _get_default_nginx_tar_path()
                
                if default_tar and default_tar.exists():
                    print(f"未找到已编译的 Nginx 版本，检测到默认压缩包，将在后台自动编译 Nginx {default_version}...")
                    print("   提示: 编译过程在后台进行，不会影响应用启动，编译完成后会自动启动 Nginx")
                    
                    # 在后台线程中执行编译和启动
                    def compile_and_start_nginx():
                        try:
                            # 将默认压缩包复制到build_root
                            build_root = _get_build_root()
                            build_root.mkdir(parents=True, exist_ok=True)
                            target_tar = build_root / f"nginx-{default_version}.tar.gz"
                            
                            shutil.copy2(default_tar, target_tar)
                            print(f"[后台任务] 已复制默认压缩包到构建目录: {target_tar}")
                            
                            # 编译nginx
                            print(f"[后台任务] 开始编译 Nginx {default_version}，这可能需要几分钟...")
                            compile_result = _compile_nginx_from_source(target_tar, default_version)
                            
                            if compile_result.success:
                                print(f"[后台任务] ✓ {compile_result.message}")
                                # 编译成功后，尝试启动
                                print(f"[后台任务] 正在自动启动 Nginx 版本 {default_version}...")
                                start_result = _start_nginx_version_internal(default_version)
                                if start_result["success"]:
                                    print(f"[后台任务] ✓ {start_result['message']}")
                                else:
                                    print(f"[后台任务] ✗ 自动启动失败: {start_result['message']}")
                            else:
                                print(f"[后台任务] ✗ 自动编译失败: {compile_result.message}")
                                if compile_result.build_log_path:
                                    print(f"[后台任务]    编译日志: {compile_result.build_log_path}")
                        except Exception as e:
                            print(f"[后台任务] ✗ 自动编译过程出错: {str(e)}")
                    
                    # 启动后台线程
                    thread = threading.Thread(target=compile_and_start_nginx, daemon=True)
                    thread.start()
                else:
                    print("提示: 未找到已编译的 Nginx 版本，请先下载并编译一个版本")
    except Exception as e:
        # 自动启动失败不影响应用启动
        print(f"⚠ 自动启动 Nginx 时出错: {str(e)}")
        print("   应用将继续启动，您可以稍后手动启动 Nginx")

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
