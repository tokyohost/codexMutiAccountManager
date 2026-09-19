"""应用配置模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.account import Account


@dataclass
class AppSettings:
    """应用偏好设置。"""

    theme: str = "system"
    auto_refresh: bool = True
    refresh_interval_minutes: int = 3
    start_with_windows: bool = False
    minimize_to_tray: bool = True
    close_to_tray: bool = True
    auto_close_codex: bool = False
    auto_start_codex: bool = False
    show_notifications: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "AppSettings":
        """从配置字典读取设置，并限制刷新间隔取值。"""
        value = value or {}
        try:
            interval = int(value.get("refreshIntervalMinutes", 3))
        except (TypeError, ValueError):
            interval = 3
        return cls(
            theme=str(value.get("theme", "system")),
            auto_refresh=bool(value.get("autoRefresh", True)),
            refresh_interval_minutes=interval if interval in (1, 3, 5, 10) else 3,
            start_with_windows=bool(value.get("startWithWindows", False)),
            minimize_to_tray=bool(value.get("minimizeToTray", True)),
            close_to_tray=bool(value.get("closeToTray", True)),
            auto_close_codex=bool(value.get("autoCloseCodex", False)),
            auto_start_codex=bool(value.get("autoStartCodex", False)),
            show_notifications=bool(value.get("showNotifications", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化设置。"""
        return {
            "theme": self.theme,
            "autoRefresh": self.auto_refresh,
            "refreshIntervalMinutes": self.refresh_interval_minutes,
            "startWithWindows": self.start_with_windows,
            "minimizeToTray": self.minimize_to_tray,
            "closeToTray": self.close_to_tray,
            "autoCloseCodex": self.auto_close_codex,
            "autoStartCodex": self.auto_start_codex,
            "showNotifications": self.show_notifications,
        }


@dataclass
class AppConfig:
    """应用持久化配置。"""

    version: int = 2
    current_account: str | None = None
    shared_home: str = ""
    settings: AppSettings = field(default_factory=AppSettings)
    accounts: list[Account] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AppConfig":
        """从配置字典构造完整配置。"""
        return cls(
            version=int(value.get("version", 1) or 1),
            current_account=value.get("currentAccount"),
            shared_home=str(value.get("sharedHome", "") or ""),
            settings=AppSettings.from_dict(value.get("settings")),
            accounts=[Account.from_dict(item) for item in value.get("accounts", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化完整配置。"""
        return {
            "version": self.version,
            "currentAccount": self.current_account,
            "sharedHome": self.shared_home,
            "settings": self.settings.to_dict(),
            "accounts": [account.to_dict() for account in self.accounts],
        }
