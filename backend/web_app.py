"""基于系统 WebView2 的桌面应用容器。"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
from pathlib import Path

import pystray
import webview
from PIL import Image

from backend.bridge.app_bridge import AppBridge
from backend.services.account_service import AccountService
from backend.services.config_service import ConfigService
from backend.services.environment_service import EnvironmentService
from backend.services.process_service import ProcessService
from backend.utils.logger import configure_logging
from backend.utils.paths import app_data_dir, frontend_index_path, resources_dir


class WebAppController:
    """组装业务服务、系统托盘和 WebView2 页面。"""

    _MUTEX_NAME = "Local\\CodexAccountManager"
    _ERROR_ALREADY_EXISTS = 183

    def __init__(self) -> None:
        """初始化账号服务和窗口状态。"""
        self.logger = configure_logging()
        self.config_service = ConfigService()
        self.environment_service = EnvironmentService()
        self.process_service = ProcessService(self.logger)
        self.account_service = AccountService(
            self.config_service,
            self.environment_service,
            self.process_service,
            self.logger,
        )
        self.window = None
        self.tray = None
        self._mutex = None
        self._stop_event = threading.Event()
        self._refresh_thread: threading.Thread | None = None
        self._force_quit = False
        self.bridge = AppBridge(self.account_service, self.logger, self.quit)

    def start(self) -> bool:
        """创建 WebView2 窗口和托盘，返回是否取得单实例。"""
        if not self._acquire_single_instance():
            return False
        index = frontend_index_path()
        if not index.is_file():
            raise FileNotFoundError(f"未找到前端构建文件：{index}；请先执行 npm run build")
        self.window = webview.create_window(
            "Codex Account Manager",
            index.resolve().as_uri(),
            js_api=self.bridge,
            width=960,
            height=680,
            min_size=(800, 560),
            background_color="#0f172a",
            hidden=True,
            confirm_close=False,
        )
        self.window.events.closing += self._on_window_closing
        self.tray = pystray.Icon(
            "codex-account-manager",
            self._load_tray_image(),
            "Codex Account Manager",
            pystray.Menu(
                pystray.MenuItem("打开管理器", self._show_window, default=True),
                pystray.MenuItem("打开日志", self._open_logs),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._exit),
            ),
        )
        return True

    def run(self) -> None:
        """启动托盘线程、自动刷新线程和 WebView2 消息循环。"""
        if not self.start():
            return
        self._refresh_thread = threading.Thread(
            target=self._refresh_loop,
            name="codex-refresh",
            daemon=True,
        )
        self._refresh_thread.start()
        self.tray.run_detached()
        try:
            webview.start(
                self._on_webview_ready,
                gui="edgechromium",
                debug=False,
                private_mode=False,
                storage_path=str(app_data_dir() / "webview2"),
                icon=str(resources_dir() / "app.ico"),
            )
        finally:
            self._stop_event.set()
            if self.tray is not None:
                self.tray.stop()
            self._release_single_instance()

    def _on_webview_ready(self) -> None:
        """在 WebView2 消息循环就绪后显示初始页面。"""
        if self.account_service.state().get("accounts"):
            return
        self._show_window()

    def _show_window(self, *_args) -> None:
        """显示并激活管理窗口。"""
        if self.window is None:
            return
        try:
            self.window.show()
            self.window.restore()
        except Exception:
            self.logger.exception("恢复管理窗口失败")

    def _on_window_closing(self) -> bool:
        """关闭窗口时按设置隐藏到托盘。"""
        if self._force_quit or not self.account_service.settings().get("closeToTray", True):
            return True
        if self.window is not None:
            self.window.hide()
        return False

    def _open_logs(self, *_args) -> None:
        """从托盘打开日志目录。"""
        from backend.utils.windows import open_path

        open_path(app_data_dir() / "logs")

    def _exit(self, *_args) -> None:
        """停止托盘、窗口和后台线程。"""
        self._force_quit = True
        self._stop_event.set()
        if self.window is not None:
            self.window.destroy()
        if self.tray is not None:
            self.tray.stop()

    def quit(self) -> None:
        """作为前端桥接回调退出应用。"""
        self._exit()

    def _refresh_loop(self) -> None:
        """按设置周期在后台刷新账号额度。"""
        elapsed = 0
        while not self._stop_event.wait(1):
            settings = self.account_service.settings()
            if not settings.get("autoRefresh"):
                elapsed = 0
                continue
            elapsed += 1
            if elapsed < int(settings.get("refreshIntervalMinutes", 3)) * 60:
                continue
            elapsed = 0
            try:
                self.account_service.refresh_all()
            except Exception:
                self.logger.exception("自动刷新账号失败")

    def _acquire_single_instance(self) -> bool:
        """使用 Windows 命名互斥量阻止重复启动。"""
        if os.name != "nt":
            return True
        self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, self._MUTEX_NAME)
        return ctypes.windll.kernel32.GetLastError() != self._ERROR_ALREADY_EXISTS

    def _release_single_instance(self) -> None:
        """释放当前进程的命名互斥量。"""
        if self._mutex:
            ctypes.windll.kernel32.CloseHandle(self._mutex)
            self._mutex = None

    @staticmethod
    def _load_tray_image() -> Image.Image:
        """读取托盘图标并转换为 RGBA 图像。"""
        path = resources_dir() / "app.ico"
        return Image.open(path).convert("RGBA")
