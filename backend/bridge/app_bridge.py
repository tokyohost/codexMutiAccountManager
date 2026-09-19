"""pywebview 对外暴露的应用桥接对象。"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from backend.services.account_service import AccountService
from backend.utils.paths import logs_dir
from backend.utils.windows import open_path


class AppBridge:
    """将后端服务包装为 Vue 可调用的 JSON 字符串接口。"""

    def __init__(
        self,
        account_service: AccountService,
        logger: logging.Logger,
        quit_callback: Callable[[], None] | None = None,
    ) -> None:
        """初始化桥接对象和退出回调。"""
        self.account_service = account_service
        self.logger = logger
        self.quit_callback = quit_callback

    def getAppState(self) -> str:
        """返回完整应用状态。"""
        return self._dump(self.account_service.state())

    def getAccounts(self) -> str:
        """返回账号列表。"""
        return self._dump(self.account_service.state().get("accounts", []))

    def getSettings(self) -> str:
        """返回应用设置。"""
        return self._dump(self.account_service.settings())

    def importCurrentAccount(self) -> str:
        """导入当前 Codex 账号。"""
        return self._submit(self.account_service.import_current_account)

    def switchAccount(self, account_id: str, close_codex: bool = False) -> str:
        """切换账号，close_codex 表示用户已确认关闭 Codex。"""
        return self._submit(lambda: self.account_service.switch_account(account_id, close_codex))

    def prepareOtherAccountLogin(self, close_codex: bool = False) -> str:
        """保存当前认证并启动处于未登录状态的 Codex。"""
        return self._submit(
            lambda: self.account_service.prepare_other_account_login(close_codex)
        )

    def refreshAccount(self, account_id: str) -> str:
        """刷新单个账号。"""
        return self._submit(lambda: self.account_service.refresh_account(account_id))

    def refreshAllAccounts(self) -> str:
        """按顺序刷新所有账号。"""
        return self._submit(self.account_service.refresh_all)

    def renameAccount(self, account_id: str, name: str) -> str:
        """修改账号名称。"""
        try:
            result = self.account_service.rename_account(account_id, name)
            return self._dump({"accepted": True, "result": result})
        except Exception as exc:
            return self._error(exc)

    def removeAccount(self, account_id: str) -> str:
        """删除账号目录。"""
        return self._submit(lambda: self.account_service.remove_account(account_id))

    def openAccountHome(self, account_id: str) -> str:
        """打开账号 CODEX_HOME 目录。"""
        try:
            account = self.account_service._find(account_id)
            open_path(account.home)
            return self._dump({"accepted": True})
        except Exception as exc:
            return self._error(exc)

    def openLogs(self) -> str:
        """打开应用日志目录。"""
        try:
            open_path(logs_dir())
            return self._dump({"accepted": True})
        except Exception as exc:
            return self._error(exc)

    def updateSettings(self, value: str) -> str:
        """更新设置并持久化。"""
        try:
            parsed = json.loads(value)
            settings = self.account_service.update_settings(parsed)
            return self._dump({"accepted": True, "settings": settings})
        except Exception as exc:
            return self._error(exc)

    def startCodex(self, account_id: str = "") -> str:
        """启动当前或指定账号的 Codex。"""
        return self._submit(lambda: self.account_service.start_codex(account_id or None))

    def quitApplication(self) -> str:
        """请求桌面应用退出。"""
        if self.quit_callback is not None:
            self.quit_callback()
        return self._dump({"accepted": True})

    def _submit(self, function: Callable[[], Any]) -> str:
        """执行桥接操作并返回统一响应。"""
        try:
            return self._dump({"accepted": True, "result": function()})
        except Exception as exc:
            return self._error(exc)

    def _error(self, error: Exception) -> str:
        """统一转换错误响应并记录异常。"""
        self.logger.exception("桥接调用失败")
        return self._dump({"accepted": False, "error": str(error)})

    @staticmethod
    def _dump(value: Any) -> str:
        """使用无 BOM 的 UTF-8 语义 JSON 序列化。"""
        return json.dumps(value, ensure_ascii=False)
