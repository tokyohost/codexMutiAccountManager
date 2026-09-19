"""账号数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.models.rate_limit import RateLimit


@dataclass
class Account:
    """表示一个被管理的 Codex 账号。"""

    id: str
    name: str
    email: str
    plan_type: str = ""
    account_type: str = ""
    home: str = ""
    created_at: int = 0
    last_refresh_at: int | None = None
    last_refresh_result: str | None = None
    status: str = "idle"
    error_message: str | None = None
    rate_limits: list[RateLimit] = field(default_factory=list)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Account":
        """从配置字典构造账号模型。"""
        return cls(
            id=str(value.get("id", "")),
            name=str(value.get("name", "未命名账号")),
            email=str(value.get("email", "")),
            plan_type=str(value.get("planType", value.get("plan_type", "")) or ""),
            account_type=str(value.get("type", value.get("accountType", "")) or ""),
            home=str(value.get("home", "")),
            created_at=int(value.get("createdAt", value.get("created_at", 0)) or 0),
            last_refresh_at=value.get("lastRefreshAt", value.get("last_refresh_at")),
            last_refresh_result=value.get("lastRefreshResult", value.get("last_refresh_result")),
            status=str(value.get("status", "idle")),
            error_message=value.get("errorMessage", value.get("error_message")),
            rate_limits=[RateLimit.from_dict(item) for item in value.get("rateLimits", [])],
        )

    def to_dict(self, current: bool = False) -> dict[str, Any]:
        """序列化为配置和前端共同使用的字段。"""
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "planType": self.plan_type,
            "type": self.account_type,
            "home": self.home,
            "createdAt": self.created_at,
            "lastRefreshAt": self.last_refresh_at,
            "lastRefreshResult": self.last_refresh_result,
            "status": self.status,
            "errorMessage": self.error_message,
            "rateLimits": [limit.to_dict() for limit in self.rate_limits],
            "current": current,
        }

