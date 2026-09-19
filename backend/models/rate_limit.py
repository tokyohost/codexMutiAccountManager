"""额度窗口相关数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitWindow:
    """表示一个额度窗口。"""

    used_percent: float = 0.0
    window_duration_mins: int = 0
    resets_at: int | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "RateLimitWindow":
        """从 App Server 返回值中构造额度窗口。"""
        value = value or {}
        try:
            used = float(value.get("usedPercent", value.get("used_percent", 0)) or 0)
        except (TypeError, ValueError):
            used = 0.0
        try:
            duration = int(value.get("windowDurationMins", value.get("window_duration_mins", 0)) or 0)
        except (TypeError, ValueError):
            duration = 0
        reset = value.get("resetsAt", value.get("resets_at"))
        try:
            reset = int(reset) if reset is not None else None
        except (TypeError, ValueError):
            reset = None
        return cls(max(0.0, min(100.0, used)), max(0, duration), reset)

    def to_dict(self) -> dict[str, Any]:
        """序列化为前端使用的驼峰字段。"""
        return {
            "usedPercent": self.used_percent,
            "windowDurationMins": self.window_duration_mins,
            "resetsAt": self.resets_at,
            "remainingPercent": max(0.0, 100.0 - self.used_percent),
        }


@dataclass
class RateLimit:
    """表示一个额度桶及其主要、次要窗口。"""

    limit_id: str = "default"
    limit_name: str = ""
    primary: RateLimitWindow = field(default_factory=RateLimitWindow)
    secondary: RateLimitWindow | None = None
    reached_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化额度信息。"""
        return {
            "limitId": self.limit_id,
            "limitName": self.limit_name,
            "primary": self.primary.to_dict(),
            "secondary": self.secondary.to_dict() if self.secondary else None,
            "rateLimitReachedType": self.reached_type,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RateLimit":
        """从配置文件中的缓存值构造额度桶。"""
        return cls(
            limit_id=str(value.get("limitId", "default")),
            limit_name=str(value.get("limitName", "") or ""),
            primary=RateLimitWindow.from_dict(value.get("primary")),
            secondary=(RateLimitWindow.from_dict(value.get("secondary")) if value.get("secondary") else None),
            reached_type=value.get("rateLimitReachedType"),
        )

