"""桌面应用启动入口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from backend.app import AppController


def main() -> None:
    """创建 Qt 应用并进入事件循环。"""
    application = QApplication(sys.argv)
    application.setApplicationName("Codex Account Manager")
    application.setApplicationDisplayName("Codex Account Manager")
    application.setOrganizationName("CodexAccountManager")
    controller = AppController(application)
    if not controller.start():
        return
    sys.exit(application.exec())

