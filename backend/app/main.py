"""
FastAPI 应用主入口
"""

import shutil
import threading
import asyncio
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi import status
import logging

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
    dynamic_services,
)
from app.routers import statistics_v2 as statistics, system
from app.utils.version import get_version
from app.utils.statistics_cache import cleanup_old_cache
from app.utils.log_watcher import start_log_watcher
from app.routers.logs import _resolve_access_log_path

# 配置全局日志（包含统计分析日志）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 初始化数据库
init_db()

# 读取当前应用版本（从配置 / 环境变量 / 默认值）
APP_VERSION = get_version()

# 创建 FastAPI 应用（版本号使用程序版本，而不是 Nginx 编译时间）
app = FastAPI(
    title="Nginx WebUI API",
    description="Nginx 管理系统的后端 API",
    version=APP_VERSION,
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
app.include_router(dynamic_services.router)
app.include_router(statistics.router)
app.include_router(system.router)


def _ensure_last_nginx_from_default_tar() -> None:
    """
    若运行版目录 last 下尚无 nginx 可执行文件，但存在默认源码包
   （backend/default-nginx/nginx-*.tar.gz），则自动编译对应版本并同步到 last。
    """
    from app.routers.nginx_manager import (
        _infer_version_from_filename,
        _get_source_tar_path,
        _upgrade_to_production_version,
        _ensure_nginx_dirs,
    )
    from app.utils.nginx_status_cache import clear_nginx_status_cache

    last_path = _get_install_path("last")
    last_exe = _get_nginx_executable(last_path)
    if last_path.exists() and last_exe.exists():
        return

    default_tar = _get_default_nginx_tar_path()
    if default_tar is None or not default_tar.exists():
        return

    version = _infer_version_from_filename(default_tar.name)
    if not version:
        logging.warning(
            "[startup] 无法从默认源码包文件名解析版本号: %s", default_tar.name
        )
        return

    _ensure_nginx_dirs()
    build_tar = _get_source_tar_path(version)
    build_tar.parent.mkdir(parents=True, exist_ok=True)
    if not build_tar.exists():
        try:
            shutil.copy2(default_tar, build_tar)
        except Exception as e:
            logging.error("[startup] 复制默认源码包到构建目录失败: %s", e)
            return

    install_path = _get_install_path(version)
    exe = _get_nginx_executable(install_path)
    if not (install_path.exists() and exe.exists()):
        print(
            f"检测到运行版 last 未就绪，正在从源码包自动编译 Nginx {version}（首次可能较慢）..."
        )
        logging.info("[startup] 自动编译 Nginx %s，源码包: %s", version, build_tar)
        result = _compile_nginx_from_source(build_tar, version, None, None)
        if not result.success:
            print(f"✗ 自动编译 Nginx 失败: {result.message}")
            if result.build_log_path:
                print(f"   编译日志: {result.build_log_path}")
            logging.error("[startup] 自动编译失败: %s", result.message)
            return
        print(f"✓ 自动编译完成: {result.message}")
        if result.build_log_path:
            print(f"   编译日志: {result.build_log_path}")

    up = _upgrade_to_production_version(version)
    if not up.get("success"):
        print(f"✗ 同步到运行版 last 失败: {up.get('message')}")
        logging.error("[startup] 同步到 last 失败: %s", up.get("message"))
        return

    clear_nginx_status_cache()
    print(f"✓ {up.get('message', '运行版 Nginx (last) 已就绪')}")


@app.on_event("startup")
async def startup_event():
    """应用启动时打印核心配置信息并自动启动nginx"""
    # 重置分析任务状态，确保重启后状态正确
    from app.routers.statistics_v2 import _state_manager

    _state_manager.reset()
    logging.info(
        "[statistics] 分析任务状态已重置，is_running=%s",
        _state_manager.get_state()["is_running"],
    )

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
        print(
            f"                   提示: 程序可以正常运行，但需要 Nginx 才能使用相关功能"
        )
        print(
            f"                   安装 Nginx 后，可通过配置文件指定 nginx.executable 路径"
        )
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

    try:
        dynamic_services.start_dynamic_registry_cleanup_scheduler()
        print("✓ 动态服务注册过期实例清理任务已启动")
    except Exception as exc:
        logging.warning("启动动态服务注册清理任务失败: %s", exc)

    # 自动启动nginx（如果有已安装的版本）
    try:
        # 无 last 时：若镜像/仓库带有默认源码包，则首次启动自动编译并同步到 last
        _ensure_last_nginx_from_default_tar()

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
                    print(
                        f"未找到最后执行的版本或发布版，将启动最新版本: {version_to_start}"
                    )

            # 启动选定的版本
            if version_to_start:
                print(f"正在自动启动 Nginx 版本 {version_to_start}...")
                result = _start_nginx_version_internal(version_to_start)

                if result["success"]:
                    print(f"✓ {result['message']}")
                else:
                    print(f"✗ 自动启动失败: {result['message']}")
            else:
                print("提示: 未找到已编译的 Nginx 版本，请通过引导页面进行初始设置")
    except Exception as e:
        # 自动启动失败不影响应用启动
        print(f"⚠ 自动启动 Nginx 时出错: {str(e)}")
        print("   应用将继续启动，您可以稍后手动启动 Nginx")

    # 启动访问日志监听：基于 pyinotify 动态触发统计分析（替代原来的纯定时任务）
    try:
        access_log_path = Path(_resolve_access_log_path())

        def _analyze_all_windows():
            """当日志有新增内容时触发：按时间范围递进分析（5分钟 -> 1小时 -> 1天）"""
            # 按时间范围递进分析：5分钟 -> 1小时 -> 1天
            # 5分钟分析：读取日志文件
            # 1小时分析：从5分钟缓存聚合
            # 1天分析：从1小时缓存聚合（如果不存在则从5分钟缓存聚合）
            # 7天和30天的数据从1天的数据中聚合，不需要单独分析

            # V2版本：使用简化的analyze_logs_simple
            try:
                from app.routers.statistics_v2 import analyze_logs_simple

                analyze_logs_simple(hours=1, full=False, trigger="watcher")
                logging.info("✓ 统计分析完成（V2）")
            except Exception as exc:
                logging.warning("基于日志监听触发的分析失败: %s", exc)

        # 防抖时间30秒，避免频繁触发
        # 结合5分钟的兜底定时任务和10秒API间隔保护
        watcher = start_log_watcher(
            access_log_path, _analyze_all_windows, debounce_seconds=30
        )
        from app.routers.statistics_v2 import _state_manager

        if watcher:
            state = _state_manager.get_state()
            state["watcher_enabled"] = True
            print(f"✓ 基于日志变化的统计分析监听已启用，文件: {access_log_path}")
        else:
            # watcher disabled
            print(
                "⚠ 未启用日志监听（可能非 Linux / 未安装 pyinotify / 日志文件不存在），"
                "将依赖手动触发全量分析"
            )
    except Exception as e:
        logging.warning(f"初始化日志监听失败，将依赖手动触发分析: {e}")

    # 兜底：每 5 分钟定时触发一次分析，防止极端情况下监听失效或长时间无请求却仍需刷新统计
    def fallback_analyzer():
        import time

        # 重启后先等待一个周期（5分钟），再开始第一次分析
        print("✓ 统计分析兜底定时任务已启动，将在 5 分钟后开始第一次分析")
        time.sleep(300)  # 等待5分钟

        while True:
            try:
                # 按时间范围递进分析：5分钟 -> 1小时 -> 1天
                # 5分钟分析：读取日志文件
                # 1小时分析：从5分钟缓存聚合
                # 1天分析：从1小时缓存聚合（如果不存在则从5分钟缓存聚合）
                # 7天和30天的数据从1天的数据中聚合，不需要单独分析

                # V2版本：使用简化的analyze_logs_simple
                try:
                    from app.routers.statistics_v2 import analyze_logs_simple

                    analyze_logs_simple(hours=1, full=False, trigger="auto_fallback")
                    logging.info("✓ 兜底定时分析完成（V2）")
                except Exception as exc:
                    logging.warning("兜底定时分析失败: %s", exc)
            except Exception as exc:
                logging.error("兜底定时分析线程异常: %s", exc)

            # 每 5 分钟兜底一次
            time.sleep(300)

    threading.Thread(target=fallback_analyzer, daemon=True).start()

    # 启动日志轮转定时任务
    def logrotate_scheduler():
        """日志轮转定时任务"""
        import time
        from app.utils.logrotate import rotate_logs
        from datetime import datetime, timedelta

        config = get_config()
        logrotate_config = config.logrotate

        if not logrotate_config.enabled:
            print("日志轮转功能已禁用，跳过定时任务启动")
            return

        print(
            f"✓ 日志轮转定时任务已启动，轮转时间: {logrotate_config.rotate_time}, 保留天数: {logrotate_config.retention_days}"
        )

        # 计算下次轮转时间
        try:
            rotate_time_parts = logrotate_config.rotate_time.split(":")
            rotate_hour = int(rotate_time_parts[0])
            rotate_minute = int(rotate_time_parts[1])
        except Exception as e:
            logging.error(f"解析轮转时间失败: {e}，使用默认时间 00:00")
            rotate_hour = 0
            rotate_minute = 0

        while True:
            try:
                now = datetime.now()
                next_rotate = now.replace(
                    hour=rotate_hour, minute=rotate_minute, second=0, microsecond=0
                )
                if next_rotate <= now:
                    # 如果今天的时间已过，则设置为明天
                    next_rotate += timedelta(days=1)

                # 计算需要等待的秒数
                wait_seconds = (next_rotate - now).total_seconds()
                logging.info(
                    f"日志轮转定时任务: 下次轮转时间 {next_rotate.strftime('%Y-%m-%d %H:%M:%S')}，"
                    f"等待 {wait_seconds:.0f} 秒"
                )

                # 等待到轮转时间
                time.sleep(wait_seconds)

                # 执行日志轮转
                logging.info("开始执行定时日志轮转...")
                result = rotate_logs(retention_days=logrotate_config.retention_days)

                if result["success"]:
                    logging.info(
                        f"定时日志轮转完成: 轮转 {len(result.get('rotated_files', []))} 个文件, "
                        f"删除 {len(result.get('deleted_files', []))} 个旧文件"
                    )
                else:
                    logging.error(f"定时日志轮转失败: {result.get('errors', [])}")
            except Exception as exc:
                logging.error(f"日志轮转定时任务异常: {exc}", exc_info=True)
                # 出错后等待 1 小时再重试
                time.sleep(3600)

    threading.Thread(target=logrotate_scheduler, daemon=True).start()

    # 启动证书自动续期定时任务（每天凌晨 3 点检查）
    def cert_renewal_scheduler():
        """证书自动续期定时任务"""
        import time
        from datetime import datetime, timedelta
        from app.utils.certbot import renew_certificate, copy_certificate_files
        from app.utils.certbot import get_certificate_info

        print("✓ 证书自动续期定时任务已启动，将在每天凌晨 3:00 检查并续期")

        while True:
            try:
                now = datetime.now()
                # 下次执行时间：明天凌晨 3 点
                next_run = now.replace(hour=3, minute=0, second=0, microsecond=0)
                if next_run <= now:
                    next_run += timedelta(days=1)

                wait_seconds = (next_run - now).total_seconds()
                logging.info(
                    f"证书自动续期定时任务: 下次执行时间 {next_run.strftime('%Y-%m-%d %H:%M:%S')}，"
                    f"等待 {wait_seconds:.0f} 秒"
                )

                time.sleep(wait_seconds)

                # 执行续期
                logging.info("开始执行证书自动续期检查...")
                result = renew_certificate(domain=None)

                if result["success"]:
                    logging.info("证书自动续期完成")

                    # 续期成功后，复制证书文件并更新数据库
                    try:
                        from app.database import SessionLocal
                        from app.models import Certificate

                        db = SessionLocal()
                        try:
                            certificates = (
                                db.query(Certificate)
                                .filter(Certificate.auto_renew == True)
                                .filter(Certificate.status == "issued")
                                .all()
                            )

                            for cert in certificates:
                                copy_result = copy_certificate_files(
                                    cert.domain, lineage_name=cert.certbot_cert_name
                                )
                                if copy_result["success"]:
                                    cert.cert_path = copy_result["cert_path"]
                                    cert.key_path = copy_result["key_path"]

                                    cert_info = get_certificate_info(cert.cert_path)
                                    if cert_info.get("valid_to"):
                                        try:
                                            cert.valid_to = datetime.fromisoformat(
                                                cert_info["valid_to"].replace(
                                                    "Z", "+00:00"
                                                )
                                            )
                                        except:
                                            pass
                                    if cert_info.get("issuer"):
                                        cert.issuer = cert_info["issuer"]

                            db.commit()
                            logging.info("证书文件已更新到持久化目录")
                        finally:
                            db.close()
                    except Exception as exc:
                        logging.error("续期后更新证书文件失败: %s", exc)
                else:
                    logging.info("证书自动续期检查完成，无需续期的证书")
            except Exception as exc:
                logging.error("证书自动续期定时任务异常: %s", exc, exc_info=True)
                time.sleep(3600)

    threading.Thread(target=cert_renewal_scheduler, daemon=True).start()

    # 启动 DNS 验证后台自动签发任务（服务运行期间保持 certbot manual 会话）
    def cert_dns_auto_issue_scheduler():
        """DNS TXT 生效后自动继续 certbot 签发，避免浏览器长时间等待。"""
        import time
        from datetime import datetime
        from app.database import SessionLocal
        from app.models import Certificate, User
        from app.utils.audit import create_audit_log
        from app.utils.certbot import (
            complete_dns_manual_challenge,
            copy_certificate_files,
            get_certificate_info,
            get_pending_dns_challenge_by_job_id,
            test_acme_directory_connectivity,
            verify_dns_txt_record,
        )
        from app.utils.nginx import apply_ssl_config

        pending_statuses = ["dns_pending"]
        print("✓ DNS 验证后台自动签发任务已启动")

        while True:
            try:
                time.sleep(30)
                db = SessionLocal()
                try:
                    pending_certs = (
                        db.query(Certificate)
                        .filter(Certificate.status.in_(pending_statuses))
                        .filter(Certificate.dns_auto_issue == True)
                        .all()
                    )
                    if pending_certs:
                        logging.info(
                            "DNS 自动签发: 发现 %s 条待处理记录",
                            len(pending_certs),
                        )

                    for cert in pending_certs:
                        logging.info(
                            "DNS 自动签发: 开始检查 domain=%s cert_id=%s job_id=%s record=%s",
                            cert.domain,
                            cert.id,
                            cert.dns_job_id,
                            cert.dns_record_name,
                        )
                        if not cert.dns_job_id or not cert.dns_record_name or not cert.dns_record_value:
                            cert.status = "failed"
                            cert.issue_error = "缺少 DNS 验证会话或 TXT 记录信息"
                            db.commit()
                            logging.warning(
                                "DNS 自动签发: 缺少会话或 TXT 信息 domain=%s cert_id=%s",
                                cert.domain,
                                cert.id,
                            )
                            continue

                        live_job = get_pending_dns_challenge_by_job_id(cert.dns_job_id)
                        if not live_job.get("success"):
                            cert.status = "expired"
                            cert.issue_error = (
                                "DNS 验证会话已过期或服务曾重启，请删除该记录后重新申请"
                            )
                            db.commit()
                            logging.warning(
                                "DNS 自动签发: 会话不可用 domain=%s cert_id=%s job_id=%s reason=%s",
                                cert.domain,
                                cert.id,
                                cert.dns_job_id,
                                live_job.get("message"),
                            )
                            continue

                        dns_check = verify_dns_txt_record(
                            cert.dns_record_name,
                            cert.dns_record_value,
                        )
                        cert.issue_output = (
                            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                            f"{dns_check.get('message') or ''}"
                        )
                        if not dns_check.get("matched"):
                            db.commit()
                            logging.info(
                                "DNS 自动签发: TXT 尚未匹配 domain=%s cert_id=%s checked_with=%s message=%s",
                                cert.domain,
                                cert.id,
                                dns_check.get("checked_with"),
                                dns_check.get("message"),
                            )
                            continue

                        logging.info(
                            "DNS 自动签发: TXT 已匹配，开始 certbot 签发 domain=%s cert_id=%s",
                            cert.domain,
                            cert.id,
                        )
                        acme_check = test_acme_directory_connectivity(timeout_sec=8.0)
                        cert.issue_output = (
                            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                            f"{acme_check.get('message')}"
                        )
                        if not acme_check.get("ok"):
                            cert.status = "failed"
                            cert.issue_error = acme_check.get("message")
                            db.commit()
                            logging.error(
                                "DNS 自动签发: ACME API 不可达 domain=%s cert_id=%s url=%s message=%s",
                                cert.domain,
                                cert.id,
                                acme_check.get("url"),
                                acme_check.get("message"),
                            )
                            continue
                        logging.info(
                            "DNS 自动签发: ACME API 可达 domain=%s cert_id=%s elapsed_ms=%s",
                            cert.domain,
                            cert.id,
                            acme_check.get("elapsed_ms"),
                        )
                        cert.status = "dns_issuing"
                        cert.issue_error = None
                        db.commit()

                        result = complete_dns_manual_challenge(cert.dns_job_id)
                        cert.issue_output = result.get("output", "")
                        if not result.get("success"):
                            cert.status = "expired" if result.get("error_code") == "invalid_job" else "failed"
                            cert.issue_error = result.get("message") or "证书签发失败"
                            db.commit()
                            logging.error(
                                "DNS 自动签发: certbot 签发失败 domain=%s cert_id=%s error_code=%s message=%s",
                                cert.domain,
                                cert.id,
                                result.get("error_code"),
                                result.get("message"),
                            )
                            try:
                                create_audit_log(
                                    db=db,
                                    user_id=cert.created_by_id,
                                    username="system",
                                    action="cert_dns_auto_issue",
                                    target=cert.domain,
                                    details={
                                        "success": False,
                                        "error_code": result.get("error_code"),
                                        "message": result.get("message"),
                                    },
                                    ip_address=None,
                                )
                            except Exception as exc:
                                logging.warning("DNS 自动签发失败审计记录失败: %s", exc)
                            continue

                        certbot_cert_name = result.get("certbot_cert_name")
                        copy_result = copy_certificate_files(
                            cert.domain, lineage_name=certbot_cert_name
                        )
                        if not copy_result.get("success"):
                            cert.status = "failed"
                            cert.issue_error = f"证书签发成功但复制文件失败: {copy_result.get('message')}"
                            db.commit()
                            logging.error(
                                "DNS 自动签发: 复制证书失败 domain=%s cert_id=%s message=%s",
                                cert.domain,
                                cert.id,
                                copy_result.get("message"),
                            )
                            continue

                        cert.cert_path = copy_result["cert_path"]
                        cert.key_path = copy_result["key_path"]
                        cert.certbot_cert_name = certbot_cert_name
                        cert.status = "issued"
                        cert.issue_method = "dns"
                        cert.auto_renew = True
                        cert.issue_error = None

                        cert_info = get_certificate_info(cert.cert_path)
                        if cert_info.get("issuer"):
                            cert.issuer = cert_info["issuer"]
                        if cert_info.get("valid_from"):
                            try:
                                cert.valid_from = datetime.fromisoformat(
                                    cert_info["valid_from"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass
                        if cert_info.get("valid_to"):
                            try:
                                cert.valid_to = datetime.fromisoformat(
                                    cert_info["valid_to"].replace("Z", "+00:00")
                                )
                            except Exception:
                                pass

                        try:
                            ssl_result = apply_ssl_config(
                                cert.domain, cert.cert_path, cert.key_path
                            )
                            ssl_message = ssl_result.get("message", "")
                        except Exception as exc:
                            ssl_message = f"自动添加 SSL 配置失败: {exc}"
                            cert.issue_error = ssl_message

                        db.commit()
                        logging.info(
                            "DNS 自动签发: 完成 domain=%s cert_id=%s cert_path=%s",
                            cert.domain,
                            cert.id,
                            cert.cert_path,
                        )

                        user = (
                            db.query(User)
                            .filter(User.id == cert.created_by_id)
                            .first()
                            if cert.created_by_id
                            else None
                        )
                        try:
                            create_audit_log(
                                db=db,
                                user_id=cert.created_by_id,
                                username=user.username if user else "system",
                                action="cert_dns_auto_issue",
                                target=cert.domain,
                                details={
                                    "success": True,
                                    "ssl_config": ssl_message,
                                    "cert_path": cert.cert_path,
                                    "key_path": cert.key_path,
                                },
                                ip_address=None,
                            )
                        except Exception as exc:
                            logging.warning("DNS 自动签发审计记录失败: %s", exc)
                finally:
                    db.close()
            except Exception as exc:
                logging.error("DNS 验证后台自动签发任务异常: %s", exc, exc_info=True)
                time.sleep(60)

    threading.Thread(target=cert_dns_auto_issue_scheduler, daemon=True).start()


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
    return {"message": "Nginx WebUI API", "version": APP_VERSION, "docs": "/docs"}


@app.get("/api/health", summary="健康检查")
async def health_check():
    """健康检查端点"""
    config = get_config()
    return {"status": "ok", "config_loaded": config is not None}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求验证错误（422）"""
    errors = exc.errors()
    error_details = []
    for error in errors:
        error_details.append(
            {
                "loc": error.get("loc"),
                "msg": error.get("msg"),
                "type": error.get("type"),
            }
        )

    # 记录详细的验证错误信息
    print(f"\n[验证错误] {request.method} {request.url}")
    print(f"[验证错误] 错误详情: {error_details}")

    # 尝试读取请求体（如果可能）
    try:
        body = await request.body()
        if body:
            print(f"[验证错误] 请求体: {body.decode('utf-8', errors='ignore')}")
    except Exception:
        pass

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": error_details},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logging.error(f"未处理的异常: {str(exc)}", exc_info=True)
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
