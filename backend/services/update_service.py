"""GitHub Release 更新检查服务预留。"""

from __future__ import annotations

import json
import urllib.request
from typing import Any


class UpdateService:
    """只读取 GitHub Release 元数据，不执行静默下载或安装。"""

    def __init__(self, repository: str = "codex-account-manager/codex-account-manager") -> None:
        """保存未来更新检查使用的仓库标识。"""
        self.repository = repository

    def check_latest(self, timeout: float = 5.0) -> dict[str, Any]:
        """读取最新 Release，网络失败时返回可展示的错误。"""
        url = f"https://api.github.com/repos/{self.repository}/releases/latest"
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
                value = json.loads(response.read().decode("utf-8"))
            return {"available": True, "tagName": value.get("tag_name"), "url": value.get("html_url")}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"available": False, "error": str(exc)}

