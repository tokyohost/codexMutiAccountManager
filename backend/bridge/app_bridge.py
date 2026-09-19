"""QWebChannel 对外暴露的应用桥接对象。"""

from __future__ import annotations

import json
import logging
from typing import Any

from PySide6.QtCore import QObject, Signal, Slot

from backend.services.account_service import AccountService, AccountServiceError
from backend.services.task_service import TaskManager
from backend.utils.paths import logs_dir
from backend.utils.windows import open_path


class AppBridge(QObject):
    """将后端服务包装为 Vue 可调用的 JSON 字符串接口。"""

    stateChanged = Signal(str)
    accountUpdated = Signal(str)
    accountsChanged = Signal(str)
    taskEvent = Signal(str)
    notification = Signal(str)

    def __init__(self, account_service: AccountService, task_manager: TaskManager, logger: logging.Logger) -> None:
        """初始化桥接对象和任务监听。"""
        super().__init__()
        self.account_service = account_service
        self.task_manager = task_manager
        self.logger = logger
        self.task_manager.task_event.connect(self._on_task_event)

    @Slot(result=str)
    def getAppState(self) -> str:
        """返回完整应用状态。"""
        return self._dump(self.account_service.state())

    @Slot(result=str)
    def getAccounts(self) -> str:
        """返回账号列表。"""
        return self._dump(self.account_service.state().get("accounts", []))

    @Slot(result=str)
    def getSettings(self) -> str:
        """返回应用设置。"""
        return self._dump(self.account_service.settings())

    @Slot(result=str)
    def importCurrentAccount(self) -> str:
        """异步导入当前 Codex 账号。"""
        return self._submit("import", self.account_service.import_current_account)

    @Slot(str, bool, result=str)
    def switchAccount(self, account_id: str, close_codex: bool = False) -> str:
        """异步切换账号，close_codex 表示用户已确认关闭 Codex。"""
        return self._submit("switch", lambda: self.account_service.switch_account(account_id, close_codex))

    @Slot(str, result=str)
    def refreshAccount(self, account_id: str) -> str:
        """异步刷新单个账号。"""
        return self._submit("refresh", lambda: self.account_service.refresh_account(account_id))

    @Slot(result=str)
    def refreshAllAccounts(self) -> str:
        """按顺序异步刷新所有账号。"""
        return self._submit("refresh_all", self.account_service.refresh_all)

    @Slot(str, str, result=str)
    def renameAccount(self, account_id: str, name: str) -> str:
        """修改账号名称。"""
        try:
            result = self.account_service.rename_account(account_id, name)
            self._emit_state()
            return self._dump({"accepted": True, "result": result})
        except Exception as exc:
            return self._error(exc)

    @Slot(str, result=str)
    def removeAccount(self, account_id: str) -> str:
        """异步删除账号目录。"""
        return self._submit("remove", lambda: self.account_service.remove_account(account_id))

    @Slot(str, result=str)
    def openAccountHome(self, account_id: str) -> str:
        """打开账号 CODEX_HOME 目录。"""
        try:
            account = self.account_service._find(account_id)
            open_path(account.home)
            return self._dump({"accepted": True})
        except Exception as exc:
            return self._error(exc)

    @Slot(result=str)
    def openLogs(self) -> str:
        """打开应用日志目录。"""
        try:
            open_path(logs_dir())
            return self._dump({"accepted": True})
        except Exception as exc:
            return self._error(exc)

    @Slot(str, result=str)
    def updateSettings(self, value: str) -> str:
        """更新设置并持久化。"""
        try:
            parsed = json.loads(value)
            settings = self.account_service.update_settings(parsed)
            self._emit_state()
            return self._dump({"accepted": True, "settings": settings})
        except Exception as exc:
            return self._error(exc)

    @Slot(str, result=str)
    def startCodex(self, account_id: str = "") -> str:
        """启动当前或指定账号的 Codex。"""
        return self._submit("start_codex", lambda: self.account_service.start_codex(account_id or None))

    @Slot(result=str)
    def quitApplication(self) -> str:
        """请求 Qt 应用退出。"""
        from PySide6.QtWidgets import QApplication

        QApplication.instance().quit()
        return self._dump({"accepted": True})

    def _submit(self, task_type: str, function: Any) -> str:
        """提交后台任务并返回任务 ID。"""
        try:
            task_id = self.task_manager.submit(task_type, function)
            return self._dump({"accepted": True, "taskId": task_id})
        except Exception as exc:
            return self._error(exc)

    @Slot(str)
    def _on_task_event(self, event: str) -> None:
        """转发任务事件，并在任务结束后推送最新状态。"""
        self.taskEvent.emit(event)
        try:
            payload = json.loads(event)
            if payload.get("event") in ("completed", "failed"):
                self._emit_state()
                result = payload.get("result")
                if isinstance(result, dict) and result.get("error"):
                    self.notification.emit(self._dump({"type": "error", "message": result["error"]}))
        except json.JSONDecodeError:
            self.logger.warning("忽略无效任务事件：%s", event)

    def _emit_state(self) -> None:
        """推送最新状态到所有前端监听者。"""
        state = self._dump(self.account_service.state())
        self.stateChanged.emit(state)
        self.accountsChanged.emit(state)

    def _error(self, error: Exception) -> str:
        """统一转换错误响应并记录异常。"""
        self.logger.exception("桥接调用失败")
        payload = {"accepted": False, "error": str(error)}
        self.notification.emit(self._dump({"type": "error", "message": str(error)}))
        return self._dump(payload)

    @staticmethod
    def _dump(value: Any) -> str:
        """使用无 BOM 的 UTF-8 语义 JSON 序列化。"""
        return json.dumps(value, ensure_ascii=False)

