"""桌面应用启动入口。"""

from __future__ import annotations

from backend.web_app import WebAppController


def main() -> None:
    """创建 WebView2 应用并进入消息循环。"""
    WebAppController().run()


if __name__ == "__main__":
    main()
