"""
基于 pyinotify 的 Nginx 访问日志动态分析器

作用：
- 监听 access.log 追加写入事件；
- 检测到有新增日志时，触发后台统计分析（替代原来的定时任务）；
- 后续可以在此基础上逐步演进为真正的“增量分析”。
"""

from __future__ import annotations

from pathlib import Path
import logging
import threading
import time
import os

from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _is_linux() -> bool:
    """简单判断当前是否为 Linux 环境"""
    return os.name == "posix" and (
        hasattr(os, "uname") and "linux" in os.uname().sysname.lower()
    )


def start_log_watcher(
    access_log_path: Path,
    analyze_callback: Callable[[], None],
    debounce_seconds: int = 10,
) -> Optional[object]:
    """
    启动基于 pyinotify 的 access.log 监听器。

    Args:
        access_log_path: 访问日志文件路径
        analyze_callback: 当检测到日志有新增内容时调用的回调函数（在独立线程中执行）
        debounce_seconds: 去抖间隔，同一段时间内多次写入只触发一次分析

    Returns:
        如果成功启动 watcher，则返回 notifier 对象；否则返回 None
    """
    if not _is_linux():
        logger.info("[log_watcher] 非 Linux 环境，跳过 pyinotify 日志监听")
        return None

    try:
        import pyinotify
    except ImportError:
        logger.warning(
            "[log_watcher] 未安装 pyinotify，无法启用基于 inotify 的日志监听；"
            "请在生产环境中安装 pyinotify 以获得更好的增量分析体验"
        )
        return None

    # 监听目录级别的事件，以便在日志文件尚未创建或被轮转时仍能捕获
    watch_dir = access_log_path.parent
    if not watch_dir.exists():
        logger.warning("[log_watcher] 日志目录不存在: %s，暂不启动监听", watch_dir)
        return None

    wm = pyinotify.WatchManager()
    # 监听修改、创建和轮转后的移动事件
    mask = pyinotify.IN_MODIFY | pyinotify.IN_CREATE | pyinotify.IN_MOVED_TO

    class _EventHandler(pyinotify.ProcessEvent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._timer: Optional[threading.Timer] = None

        def _schedule_trigger(self):
            # 取消已有的定时任务，合并多次文件变更
            if self._timer is not None and self._timer.is_alive():
                self._timer.cancel()

            def _fire():
                logger.info(
                    "[log_watcher] 访问日志在最近 %s 秒内有更新，开始触发合并后的后台分析",
                    debounce_seconds,
                )
                # 在独立线程中调用回调，避免阻塞 inotify 事件循环
                threading.Thread(target=analyze_callback, daemon=True).start()

            self._timer = threading.Timer(debounce_seconds, _fire)
            self._timer.daemon = True
            self._timer.start()

        def _maybe_trigger(self, event_path: str):
            # 只关心目标文件（按文件名匹配，兼容轮转/重建）
            if Path(event_path).name != access_log_path.name:
                return

            # 不立即触发，延迟 debounce_seconds 秒合并触发
            self._schedule_trigger()

        def process_IN_MODIFY(self, event):  # type: ignore[override]
            self._maybe_trigger(event.pathname)

        def process_IN_CREATE(self, event):  # type: ignore[override]
            self._maybe_trigger(event.pathname)

        def process_IN_MOVED_TO(self, event):  # type: ignore[override]
            self._maybe_trigger(event.pathname)

    handler = _EventHandler()
    notifier = pyinotify.ThreadedNotifier(wm, handler)

    wm.add_watch(str(watch_dir), mask)
    notifier.start()

    logger.info(
        "[log_watcher] 已启动访问日志监听: 目录=%s, 文件名=%s",
        watch_dir,
        access_log_path.name,
    )
    return notifier
