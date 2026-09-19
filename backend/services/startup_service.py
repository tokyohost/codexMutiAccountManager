"""Windows 开机启动服务。"""

from __future__ import annotations

import sys
from pathlib import Path


class StartupService:
    """管理当前用户的开机启动注册表项。"""

    RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
    VALUE_NAME = "CodexAccountManager"

    def set_enabled(self, enabled: bool, executable: str | None = None) -> None:
        """启用或关闭当前用户开机启动。"""
        if sys.platform != "win32":
            return
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.RUN_KEY) as key:
            if enabled:
                if executable:
                    command = executable
                elif getattr(sys, "frozen", False):
                    command = str(Path(sys.executable).resolve())
                else:
                    entry = Path(__file__).resolve().parents[2] / "main.py"
                    command = f'"{sys.executable}" "{entry}"'
                winreg.SetValueEx(key, self.VALUE_NAME, 0, winreg.REG_SZ, command)
            else:
                try:
                    winreg.DeleteValue(key, self.VALUE_NAME)
                except FileNotFoundError:
                    pass
