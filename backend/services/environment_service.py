"""CODEX_HOME 与用户环境变量服务。"""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


class EnvironmentService:
    """读取和更新进程、注册表中的 CODEX_HOME。"""

    def get_current_home(self) -> Path:
        """按进程环境、注册表、默认目录顺序解析当前 Codex Home。"""
        value = os.environ.get("CODEX_HOME")
        if value:
            return Path(value).expanduser()
        if sys.platform == "win32":
            try:
                import winreg

                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
                    value, _ = winreg.QueryValueEx(key, "CODEX_HOME")
                    if value:
                        return Path(str(value)).expanduser()
            except (FileNotFoundError, OSError):
                pass
        return Path.home() / ".codex"

    def set_home(self, home: str | Path) -> None:
        """更新当前进程和 HKCU Environment 中的 CODEX_HOME，并广播变更。"""
        path = str(Path(home).expanduser().resolve())
        os.environ["CODEX_HOME"] = path
        if sys.platform != "win32":
            return
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            winreg.SetValueEx(key, "CODEX_HOME", 0, winreg.REG_EXPAND_SZ, path)
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        SMTO_ABORTIFHUNG = 0x0002
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", SMTO_ABORTIFHUNG, 5000, None
        )

