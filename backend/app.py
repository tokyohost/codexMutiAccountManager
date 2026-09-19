"""桌面应用兼容入口。"""

from __future__ import annotations

from backend.web_app import WebAppController


class AppController(WebAppController):
    """兼容旧名称的 WebView2 应用控制器。"""

    def __init__(self, _application: object | None = None) -> None:
        """忽略旧版应用对象，使用新的 WebView2 控制器初始化。"""
        super().__init__()


__all__ = ["AppController"]
