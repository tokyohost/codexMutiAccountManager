"""PySide6 应用壳层、托盘和本地 Vue 页面容器。"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from backend.bridge.app_bridge import AppBridge
from backend.services.account_service import AccountService
from backend.services.config_service import ConfigService
from backend.services.environment_service import EnvironmentService
from backend.services.process_service import ProcessService
from backend.services.task_service import TaskManager
from backend.utils.logger import configure_logging
from backend.utils.paths import frontend_index_path, resources_dir
from backend.utils.single_instance import SingleInstanceGuard


class MainWindow(QMainWindow):
    """承载 QWebEngineView 的主窗口。"""

    def __init__(self, bridge: AppBridge, close_to_tray: Callable[[], bool]) -> None:
        """创建主窗口和 WebChannel。"""
        super().__init__()
        self.bridge = bridge
        self.close_to_tray = close_to_tray
        self.setWindowTitle("Codex Account Manager")
        self.resize(960, 680)
        self.view = QWebEngineView(self)
        self.setCentralWidget(self.view)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("appBridge", bridge)
        self.view.page().setWebChannel(self.channel)

    def closeEvent(self, event) -> None:
        """按设置隐藏到托盘或真正关闭。"""
        if self.close_to_tray():
            self.hide()
            event.ignore()
        else:
            event.accept()


class AppController:
    """组装服务、托盘、主窗口和定时刷新。"""

    def __init__(self, application: QApplication) -> None:
        """初始化应用依赖。"""
        self.application = application
        self.logger = configure_logging()
        self.guard = SingleInstanceGuard("CodexAccountManager.SingleInstance")
        self.config_service = ConfigService()
        self.environment_service = EnvironmentService()
        self.process_service = ProcessService(self.logger)
        self.account_service = AccountService(
            self.config_service,
            self.environment_service,
            self.process_service,
            self.logger,
        )
        self.task_manager = TaskManager(self.logger)
        self.bridge = AppBridge(self.account_service, self.task_manager, self.logger)
        self.window = MainWindow(self.bridge, self._close_to_tray)
        self.tray = QSystemTrayIcon(self._icon(), self.application)
        self.tray_menu = QMenu()
        self.refresh_timer = QTimer(self.application)
        self.refresh_timer.timeout.connect(self._auto_refresh)
        self._force_quit = False

    def start(self) -> bool:
        """获取单实例并完成 UI、托盘和页面初始化。"""
        if not self.guard.acquire():
            return False
        self.guard.activateRequested.connect(self.show_window)
        self.tray.activated.connect(self._tray_activated)
        self._setup_tray()
        self.bridge.stateChanged.connect(self._on_state_changed)
        self._load_page()
        self._configure_timer()
        self.application.aboutToQuit.connect(self._cleanup)
        self.tray.show()
        if not self.account_service.state()["accounts"]:
            self.show_window()
        return True

    def _load_page(self) -> None:
        """加载开发 URL 或本地生产 dist/index.html。"""
        dev_url = os.environ.get("CODEX_MANAGER_DEV_URL")
        if dev_url:
            self.window.view.load(QUrl(dev_url))
            return
        index = frontend_index_path()
        if index.exists():
            self.window.view.load(QUrl.fromLocalFile(str(index)))
            return
        QMessageBox.warning(self.window, "前端资源缺失", f"未找到前端构建文件：{index}\n请先执行 npm run build。")

    def _setup_tray(self) -> None:
        """根据最新账号列表构建托盘菜单。"""
        self.tray_menu.clear()
        title = self.tray_menu.addAction("Codex Account Manager")
        title.setEnabled(False)
        self.tray_menu.addSeparator()
        state = self.account_service.state()
        for account in state["accounts"]:
            action = QAction(("✓ " if account["current"] else "  ") + account["name"], self.tray_menu)
            action.triggered.connect(lambda _checked=False, account_id=account["id"]: self._tray_switch(account_id))
            self.tray_menu.addAction(action)
        if state["accounts"]:
            self.tray_menu.addSeparator()
        open_action = self.tray_menu.addAction("打开管理器")
        open_action.triggered.connect(self.show_window)
        refresh_action = self.tray_menu.addAction("刷新所有额度")
        refresh_action.triggered.connect(self.bridge.refreshAllAccounts)
        import_action = self.tray_menu.addAction("添加当前账号")
        import_action.triggered.connect(self.bridge.importCurrentAccount)
        self.tray_menu.addSeparator()
        quit_action = self.tray_menu.addAction("退出")
        quit_action.triggered.connect(self.quit)
        self.tray.setContextMenu(self.tray_menu)

    def _tray_switch(self, account_id: str) -> None:
        """从托盘发起切换，默认不自动关闭已运行 Codex。"""
        self.bridge.switchAccount(account_id, False)

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """双击托盘图标时显示管理窗口。"""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_window()

    def _configure_timer(self) -> None:
        """按当前设置配置自动刷新计时器。"""
        settings = self.account_service.settings()
        self.refresh_timer.stop()
        if settings.get("autoRefresh"):
            self.refresh_timer.start(int(settings.get("refreshIntervalMinutes", 3)) * 60 * 1000)

    def _on_state_changed(self, _state: str) -> None:
        """状态变化后同步托盘菜单和自动刷新计时器。"""
        self._setup_tray()
        self._configure_timer()

    def _auto_refresh(self) -> None:
        """触发后台批量刷新。"""
        if self.account_service.state()["accounts"]:
            self.bridge.refreshAllAccounts()

    def show_window(self) -> None:
        """显示并激活主窗口。"""
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def _close_to_tray(self) -> bool:
        """读取关闭窗口行为设置。"""
        return bool(self.account_service.settings().get("closeToTray", True)) and not self._force_quit

    def quit(self) -> None:
        """通过托盘退出应用。"""
        self._force_quit = True
        self.application.quit()

    def _cleanup(self) -> None:
        """清理托盘和本地单实例服务。"""
        self.tray.hide()
        QLocalServer.removeServer("CodexAccountManager.SingleInstance")

    @staticmethod
    def _icon() -> QIcon:
        """加载资源图标，缺失时使用 Qt 默认图标。"""
        path = resources_dir() / "tray.svg"
        return QIcon(str(path)) if path.exists() else QApplication.style().standardIcon(QApplication.style().SP_ComputerIcon)
