"""账号导入、切换和额度读取服务。"""

from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from threading import RLock
from typing import Any

from backend.models.account import Account
from backend.models.config import AppConfig
from backend.models.rate_limit import RateLimit, RateLimitWindow
from backend.services.codex_app_server import CodexAppServerClient, CodexAppServerError
from backend.services.config_service import ConfigService
from backend.services.environment_service import EnvironmentService
from backend.services.process_service import ProcessService
from backend.utils.paths import accounts_dir


class AccountServiceError(RuntimeError):
    """表示用户可理解的账号业务错误。"""


class AccountService:
    """实现账号生命周期，并确保导入后的 Home 独立可用。"""

    def __init__(
        self,
        config_service: ConfigService,
        environment_service: EnvironmentService,
        process_service: ProcessService,
        logger: logging.Logger,
    ) -> None:
        """加载配置并初始化服务依赖。"""
        self.config_service = config_service
        self.environment_service = environment_service
        self.process_service = process_service
        self.logger = logger
        self.config: AppConfig = config_service.load()
        self._lock = RLock()

    def state(self) -> dict[str, Any]:
        """返回前端所需的非敏感完整状态。"""
        with self._lock:
            current = self.config.current_account
            return {
                "currentAccount": current,
                "accounts": [account.to_dict(account.id == current) for account in self.config.accounts],
                "settings": self.config.settings.to_dict(),
                "configLoadError": self.config_service.load_error,
            }

    def settings(self) -> dict[str, Any]:
        """返回应用设置。"""
        with self._lock:
            return self.config.settings.to_dict()

    def update_settings(self, value: dict[str, Any]) -> dict[str, Any]:
        """更新设置并同步开机启动选项。"""
        from backend.services.startup_service import StartupService

        with self._lock:
            old = self.config.settings.to_dict()
            old.update(value)
            from backend.models.config import AppSettings

            self.config.settings = AppSettings.from_dict(old)
            self.config_service.save(self.config)
            StartupService().set_enabled(self.config.settings.start_with_windows)
            return self.config.settings.to_dict()

    def import_current_account(self) -> dict[str, Any]:
        """读取当前账号、复制 Home、二次验证后再写入配置。"""
        source_home = self.environment_service.get_current_home().expanduser().resolve()
        if not source_home.is_dir():
            raise AccountServiceError(f"当前 CODEX_HOME 不存在：{source_home}")
        source_info = self._read_account(source_home)
        email = self._email_from(source_info)
        if not email:
            raise AccountServiceError("当前 Codex 未登录或 App Server 未返回邮箱")
        with self._lock:
            if any(account.email.casefold() == email.casefold() for account in self.config.accounts):
                raise AccountServiceError("该账号已经添加")
            if any(self._same_path(account.home, source_home) for account in self.config.accounts):
                raise AccountServiceError("该 CODEX_HOME 已经添加")
        account_id = str(uuid.uuid4())
        account_root = accounts_dir() / account_id
        temporary_home = account_root / "codex_home.importing"
        managed_home = account_root / "codex_home"
        account_root.mkdir(parents=True, exist_ok=False)
        try:
            shutil.copytree(source_home, temporary_home)
            managed_info = self._read_account(temporary_home)
            if self._email_from(managed_info).casefold() != email.casefold():
                raise AccountServiceError("导入后二次验证失败：账号邮箱不一致")
            os.replace(temporary_home, managed_home)
            now = int(time.time())
            account = Account(
                id=account_id,
                name=self._display_name(email),
                email=email,
                plan_type=self._plan_type(source_info),
                account_type=self._account_type(source_info),
                home=str(managed_home),
                created_at=now,
                status="ready",
            )
            with self._lock:
                self.config.accounts.append(account)
                self.config_service.save(self.config)
            self.logger.info("账号导入成功 id=%s email=%s home=%s", account_id, email, managed_home)
            return {"accountId": account_id, "email": email, "suggestSwitch": True}
        except Exception:
            shutil.rmtree(account_root, ignore_errors=True)
            raise

    def refresh_account(self, account_id: str) -> dict[str, Any]:
        """刷新一个账号的额度并缓存非敏感结果。"""
        account = self._find(account_id)
        with self._lock:
            account.status = "loading"
            account.error_message = None
        try:
            with CodexAppServerClient(account.home, self.logger) as client:
                info = client.read_account()
                limits = client.read_rate_limits()
            with self._lock:
                account.plan_type = self._plan_type(info) or account.plan_type
                account.rate_limits = self._parse_rate_limits(limits)
                account.last_refresh_at = int(time.time())
                account.last_refresh_result = "success"
                account.status = "ready"
                account.error_message = None
                self.config_service.save(self.config)
            return {"accountId": account_id, "status": "ready"}
        except Exception as exc:
            status = self._status_for_error(exc)
            with self._lock:
                account.status = status
                account.last_refresh_at = int(time.time())
                account.last_refresh_result = "failed"
                account.error_message = str(exc)
                self.config_service.save(self.config)
            self.logger.warning("刷新账号失败 id=%s: %s", account_id, exc)
            return {"accountId": account_id, "status": status, "error": str(exc)}

    def refresh_all(self) -> dict[str, Any]:
        """按顺序刷新所有账号，单个失败不会中断后续账号。"""
        results = [self.refresh_account(account.id) for account in list(self.config.accounts)]
        return {"results": results}

    def switch_account(self, account_id: str, close_codex: bool = False) -> dict[str, Any]:
        """切换注册表 CODEX_HOME，必要时先关闭 Codex 进程。"""
        account = self._find(account_id)
        running = self.process_service.find_codex_processes()
        if running and not close_codex:
            return {"success": False, "code": "codex_running", "accountId": account_id}
        if running and not self.process_service.close_codex():
            return {"success": False, "code": "close_failed", "message": "无法关闭正在运行的 Codex"}
        home = Path(account.home)
        if not home.is_dir():
            raise AccountServiceError(f"账号 CODEX_HOME 不存在：{home}")
        self.environment_service.set_home(home)
        with self._lock:
            self.config.current_account = account_id
            self.config_service.save(self.config)
        self.logger.info("账号切换成功 id=%s email=%s home=%s", account.id, account.email, home)
        return {"success": True, "accountId": account_id, "home": str(home)}

    def rename_account(self, account_id: str, name: str) -> dict[str, Any]:
        """修改账号显示名称。"""
        account = self._find(account_id)
        clean_name = name.strip()
        if not clean_name:
            raise AccountServiceError("账号名称不能为空")
        with self._lock:
            account.name = clean_name[:80]
            self.config_service.save(self.config)
        return {"accountId": account_id, "name": account.name}

    def remove_account(self, account_id: str) -> dict[str, Any]:
        """删除非当前账号及其完整 CODEX_HOME。"""
        with self._lock:
            if self.config.current_account == account_id:
                raise AccountServiceError("当前账号不能删除，请先切换到其他账号")
            account = self._find(account_id)
            account_root = Path(account.home).expanduser().resolve().parent
            managed_root = accounts_dir().resolve()
            if managed_root not in account_root.parents:
                raise AccountServiceError("账号目录不在应用管理范围内，已拒绝删除")
        shutil.rmtree(account_root, ignore_errors=False)
        with self._lock:
            self.config.accounts.remove(account)
            self.config_service.save(self.config)
        self.logger.info("账号已删除 id=%s email=%s", account.id, account.email)
        return {"accountId": account_id}

    def start_codex(self, account_id: str | None = None) -> dict[str, Any]:
        """以目标账号 Home 启动 Codex，避免继承旧终端环境。"""
        account_id = account_id or self.config.current_account
        if not account_id:
            raise AccountServiceError("尚未选择当前账号")
        account = self._find(account_id)
        executable = os.environ.get("CODEX_EXECUTABLE") or shutil.which("codex")
        if not executable:
            raise AccountServiceError("未找到 codex 命令")
        env = os.environ.copy()
        env["CODEX_HOME"] = account.home
        import subprocess

        subprocess.Popen([executable], env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        return {"accountId": account.id}

    def _read_account(self, home: Path) -> dict[str, Any]:
        """在指定 Home 中读取账号信息。"""
        if not home.is_dir():
            raise AccountServiceError(f"CODEX_HOME 不存在：{home}")
        try:
            with CodexAppServerClient(str(home), self.logger) as client:
                return client.read_account()
        except CodexAppServerError as exc:
            message = str(exc)
            if "credential" in message.lower() or "auth" in message.lower():
                message += "；当前登录凭据可能位于 Windows Credential Manager，请设置 cli_auth_credentials_store = \"file\" 后重新登录。"
            raise AccountServiceError(message) from exc

    def _find(self, account_id: str) -> Account:
        """查找账号，不存在时抛出用户可理解的错误。"""
        with self._lock:
            for account in self.config.accounts:
                if account.id == account_id:
                    return account
        raise AccountServiceError("账号不存在或已被删除")

    @staticmethod
    def _same_path(first: str, second: Path) -> bool:
        """比较两个 Home 的真实路径。"""
        try:
            return Path(first).expanduser().resolve() == second.resolve()
        except OSError:
            return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))

    @staticmethod
    def _account_payload(value: dict[str, Any]) -> dict[str, Any]:
        """兼容 account/read 直接返回或嵌套 account 的两种结构。"""
        nested = value.get("account")
        return nested if isinstance(nested, dict) else value

    @classmethod
    def _email_from(cls, value: dict[str, Any]) -> str:
        """读取账号邮箱。"""
        payload = cls._account_payload(value)
        return str(payload.get("email", "") or "").strip()

    @classmethod
    def _plan_type(cls, value: dict[str, Any]) -> str:
        """读取订阅类型。"""
        payload = cls._account_payload(value)
        return str(payload.get("planType", payload.get("plan_type", "")) or "")

    @classmethod
    def _account_type(cls, value: dict[str, Any]) -> str:
        """读取账号类型。"""
        payload = cls._account_payload(value)
        return str(payload.get("type", "") or "")

    @staticmethod
    def _display_name(email: str) -> str:
        """从邮箱生成初始显示名。"""
        return f"{email.split('@', 1)[0]} Plus"

    @staticmethod
    def _parse_rate_limits(value: dict[str, Any]) -> list[RateLimit]:
        """解析新旧两种额度桶返回结构。"""
        buckets = value.get("rateLimitsByLimitId")
        if isinstance(buckets, dict):
            items = list(buckets.items())
        else:
            legacy = value.get("rateLimits", value)
            items = [("default", legacy)] if isinstance(legacy, dict) else []
        result: list[RateLimit] = []
        for key, item in items:
            if not isinstance(item, dict):
                continue
            primary = item.get("primary") or {}
            secondary = item.get("secondary")
            result.append(
                RateLimit(
                    limit_id=str(item.get("limitId", key)),
                    limit_name=str(item.get("limitName", "") or ""),
                    primary=RateLimitWindow.from_dict(primary),
                    secondary=(
                        RateLimitWindow.from_dict(secondary)
                        if isinstance(secondary, dict)
                        else None
                    ),
                    reached_type=item.get("rateLimitReachedType"),
                )
            )
        return result

    @staticmethod
    def _status_for_error(error: Exception) -> str:
        """将常见异常映射为前端状态。"""
        message = str(error).lower()
        if "未找到 codex" in message or "app server" in message:
            return "codex_unavailable"
        if any(word in message for word in ("auth", "登录", "credential", "token")):
            return "auth_error"
        if any(word in message for word in ("network", "网络", "timeout", "超时")):
            return "network_error"
        return "error"
