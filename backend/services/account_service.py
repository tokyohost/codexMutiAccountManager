"""账号导入、切换和额度读取服务。"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
import uuid
from pathlib import Path
from threading import Lock, RLock
from typing import Any

from backend.models.account import Account
from backend.models.config import AppConfig
from backend.models.rate_limit import RateLimit, RateLimitWindow
from backend.services.codex_app_server import CodexAppServerClient, CodexAppServerError
from backend.services.codex_locator import resolve_codex_executable
from backend.services.config_service import ConfigService
from backend.services.environment_service import EnvironmentService
from backend.services.process_service import ProcessService
from backend.utils.paths import accounts_dir


class AccountServiceError(RuntimeError):
    """表示用户可理解的账号业务错误。"""


class AccountService:
    """通过共享 CODEX_HOME 和独立认证快照实现账号生命周期。"""

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
        self._import_lock = Lock()
        self._auth_lock = RLock()

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
        """以非阻塞互斥方式导入当前账号，避免重复点击创建并发快照。"""
        if not self._import_lock.acquire(blocking=False):
            raise AccountServiceError("当前账号正在导入，请勿重复操作")
        try:
            return self._import_current_account()
        finally:
            self._import_lock.release()

    def _import_current_account(self) -> dict[str, Any]:
        """读取当前账号并仅保存 auth.json 登录快照。"""
        source_home = self.environment_service.get_current_home().expanduser().resolve()
        if not source_home.is_dir():
            raise AccountServiceError(f"当前 CODEX_HOME 不存在：{source_home}")
        with self._auth_lock:
            shared_home = self._shared_home()
            if self.config.shared_home and not self._same_path(str(shared_home), source_home):
                raise AccountServiceError(
                    f"当前 CODEX_HOME 与账号管理器的共享目录不一致：{shared_home}"
                )
            source_info = self._read_account(source_home)
            email = self._email_from(source_info)
            if not email:
                raise AccountServiceError("当前 Codex 未登录或 App Server 未返回邮箱")
            with self._lock:
                if any(account.email.casefold() == email.casefold() for account in self.config.accounts):
                    raise AccountServiceError("该账号已经添加")

            source_auth = source_home / "auth.json"
            auth_bytes = self._read_auth_bytes(source_auth)
            account_id = str(uuid.uuid4())
            account_root = accounts_dir() / account_id
            snapshot_path = account_root / "auth.json"
            account_root.mkdir(parents=True, exist_ok=False)
            previous_current = self.config.current_account
            previous_shared_home = self.config.shared_home
            previous_version = self.config.version
            try:
                self._atomic_write_bytes(snapshot_path, auth_bytes)
                managed_info = self._read_snapshot_account(snapshot_path)
                if self._email_from(managed_info).casefold() != email.casefold():
                    raise AccountServiceError("导入后二次验证失败：账号邮箱不一致")
                account = Account(
                    id=account_id,
                    name=self._display_name(email),
                    email=email,
                    plan_type=self._plan_type(source_info),
                    account_type=self._account_type(source_info),
                    home=str(source_home),
                    auth_path=str(snapshot_path),
                    created_at=int(time.time()),
                    status="ready",
                )
                with self._lock:
                    self.config.version = 2
                    self.config.shared_home = str(source_home)
                    self.config.current_account = account_id
                    self.config.accounts.append(account)
                    try:
                        self.config_service.save(self.config)
                    except Exception:
                        # 配置持久化失败时同步回滚内存，避免留下幽灵账号。
                        self.config.accounts.remove(account)
                        self.config.current_account = previous_current
                        self.config.shared_home = previous_shared_home
                        self.config.version = previous_version
                        raise
                self.logger.info(
                    "账号认证快照导入成功 id=%s email=%s home=%s", account_id, email, source_home
                )
                return {"accountId": account_id, "email": email, "suggestSwitch": False}
            except Exception:
                shutil.rmtree(account_root, ignore_errors=True)
                raise

    def _read_snapshot_account(self, snapshot_path: Path) -> dict[str, Any]:
        """在临时最小 Home 中验证认证快照，不接触活动 auth.json。"""
        temporary_home = snapshot_path.parent / f"verify-{uuid.uuid4().hex}"
        try:
            temporary_home.mkdir(parents=True, exist_ok=False)
            self._atomic_write_bytes(temporary_home / "auth.json", self._read_auth_bytes(snapshot_path))
            self._write_file_credential_config(temporary_home)
            info = self._read_account(temporary_home)
            refreshed_auth = temporary_home / "auth.json"
            if refreshed_auth.is_file():
                self._atomic_write_bytes(snapshot_path, self._read_auth_bytes(refreshed_auth))
            return info
        finally:
            shutil.rmtree(temporary_home, ignore_errors=True)

    @staticmethod
    def _read_auth_bytes(path: Path) -> bytes:
        """读取并校验 auth.json 的基本结构，但不记录其中的敏感内容。"""
        if not path.is_file():
            raise AccountServiceError(
                f"未找到登录文件：{path}；请设置 cli_auth_credentials_store = \"file\" 后重新登录"
            )
        try:
            data = path.read_bytes()
            value = json.loads(data.decode("utf-8-sig"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AccountServiceError(f"登录文件不可读取或格式错误：{path}") from exc
        if not isinstance(value, dict) or not value:
            raise AccountServiceError("登录文件内容无效，请重新登录 Codex")
        return data

    @staticmethod
    def _atomic_write_bytes(path: Path, data: bytes) -> None:
        """在目标目录内通过临时文件和原子替换写入认证快照。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass

    def _shared_home(self) -> Path:
        """返回全账号共用的活动 CODEX_HOME。"""
        if self.config.shared_home:
            return Path(self.config.shared_home).expanduser().resolve()
        return self.environment_service.get_current_home().expanduser().resolve()

    def _write_file_credential_config(self, home: Path) -> None:
        """为临时验证 Home 强制指定文件凭据，避免系统 Keyring 串号。"""
        self._atomic_write_bytes(
            home / "config.toml", b'cli_auth_credentials_store = "file"\n'
        )

    def _snapshot_path(self, account: Account, migrate: bool = True) -> Path:
        """返回账号认证快照路径，并按需兼容迁移旧版完整 Home。"""
        if account.auth_path:
            return Path(account.auth_path).expanduser().resolve()
        legacy_auth = Path(account.home).expanduser().resolve() / "auth.json"
        if not migrate:
            return legacy_auth
        snapshot_path = accounts_dir() / account.id / "auth.json"
        self._atomic_write_bytes(snapshot_path, self._read_auth_bytes(legacy_auth))
        account.auth_path = str(snapshot_path)
        account.home = str(self._shared_home())
        self.config.version = 2
        self.config.shared_home = account.home
        self.config_service.save(self.config)
        self.logger.info("旧版账号已迁移为认证快照 id=%s", account.id)
        return snapshot_path

    def refresh_account(self, account_id: str) -> dict[str, Any]:
        """刷新一个账号的额度并缓存非敏感结果。"""
        account = self._find(account_id)
        with self._lock:
            account.status = "loading"
            account.error_message = None
        try:
            with self._auth_lock:
                shared_home = self._shared_home()
                temporary_home: Path | None = None
                snapshot_path = self._snapshot_path(account)
                if self.config.current_account == account.id:
                    operation_home = shared_home
                else:
                    temporary_home = snapshot_path.parent / f"refresh-{uuid.uuid4().hex}"
                    temporary_home.mkdir(parents=True, exist_ok=False)
                    self._atomic_write_bytes(
                        temporary_home / "auth.json", self._read_auth_bytes(snapshot_path)
                    )
                    self._write_file_credential_config(temporary_home)
                    operation_home = temporary_home
                try:
                    with CodexAppServerClient(str(operation_home), self.logger) as client:
                        info = client.read_account()
                        limits = client.read_rate_limits()
                    if self._email_from(info).casefold() != account.email.casefold():
                        raise AccountServiceError("额度刷新返回了其他账号，已拒绝更新认证快照")
                    refreshed_auth = operation_home / "auth.json"
                    if refreshed_auth.is_file():
                        self._atomic_write_bytes(
                            snapshot_path, self._read_auth_bytes(refreshed_auth)
                        )
                finally:
                    if temporary_home is not None:
                        shutil.rmtree(temporary_home, ignore_errors=True)
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
        """原子替换共享 Home 的 auth.json，失败时恢复原登录状态。"""
        account = self._find(account_id)
        if self.config.current_account == account_id:
            return {"success": True, "accountId": account_id, "home": str(self._shared_home())}
        running = self.process_service.find_codex_processes()
        if running and not close_codex:
            return {"success": False, "code": "codex_running", "accountId": account_id}
        if running and not self.process_service.close_codex():
            return {"success": False, "code": "close_failed", "message": "无法关闭正在运行的 Codex"}
        with self._auth_lock:
            home = self._shared_home()
            if not home.is_dir():
                raise AccountServiceError(f"共享 CODEX_HOME 不存在：{home}")
            live_auth = home / "auth.json"
            original_auth = self._read_auth_bytes(live_auth) if live_auth.is_file() else None
            target_auth = self._read_auth_bytes(self._snapshot_path(account))
            previous_current = self.config.current_account
            previous_shared_home = self.config.shared_home
            previous_version = self.config.version
            previous_account_home = account.home

            # 切走前先采纳 Codex 可能已经轮换的 Token，但必须确认活动文件仍属于当前账号。
            if previous_current and original_auth is not None:
                try:
                    current = self._find(previous_current)
                    live_info = self._read_account(home)
                    if self._email_from(live_info).casefold() == current.email.casefold():
                        original_auth = self._read_auth_bytes(live_auth)
                        self._atomic_write_bytes(self._snapshot_path(current), original_auth)
                    else:
                        self.logger.warning("活动登录与当前账号不一致，跳过旧账号认证同步")
                except Exception as exc:
                    self.logger.warning("切换前同步当前账号认证失败，继续使用已有快照：%s", exc)

            try:
                self._atomic_write_bytes(live_auth, target_auth)
                target_info = self._read_account(home)
                if self._email_from(target_info).casefold() != account.email.casefold():
                    raise AccountServiceError(
                        "切换后二次验证失败：账号邮箱不一致；请确认 "
                        'cli_auth_credentials_store = "file"'
                    )
                self._atomic_write_bytes(
                    self._snapshot_path(account), self._read_auth_bytes(live_auth)
                )
                self.environment_service.set_home(home)
                with self._lock:
                    self.config.version = 2
                    self.config.shared_home = str(home)
                    self.config.current_account = account_id
                    account.home = str(home)
                    try:
                        self.config_service.save(self.config)
                    except Exception:
                        self.config.current_account = previous_current
                        self.config.shared_home = previous_shared_home
                        self.config.version = previous_version
                        account.home = previous_account_home
                        raise
            except Exception:
                if original_auth is None:
                    live_auth.unlink(missing_ok=True)
                else:
                    self._atomic_write_bytes(live_auth, original_auth)
                raise
        self.logger.info("账号切换成功 id=%s email=%s home=%s", account.id, account.email, home)
        return {"success": True, "accountId": account_id, "home": str(home)}

    def prepare_other_account_login(self, close_codex: bool = False) -> dict[str, Any]:
        """保留当前认证快照并移走活动认证，使 Codex 进入未登录状态。"""
        running = self.process_service.find_codex_processes()
        if running and not close_codex:
            return {"success": False, "code": "codex_running"}
        if running and not self.process_service.close_codex():
            return {"success": False, "code": "close_failed", "message": "无法关闭正在运行的 Codex"}

        # 提前检查可执行文件，避免清除活动认证后才发现无法启动登录界面。
        executable = resolve_codex_executable()
        if not executable:
            raise AccountServiceError(
                "未找到 Codex CLI，请确认已安装 Codex；应用已自动检查 PATH、npm 全局目录和常见安装目录"
            )

        with self._auth_lock:
            home = self._shared_home()
            if not home.is_dir():
                raise AccountServiceError(f"共享 CODEX_HOME 不存在：{home}")
            live_auth = home / "auth.json"
            if not live_auth.is_file():
                raise AccountServiceError("Codex 当前已处于未登录状态，请直接完成新账号登录")

            original_auth = self._read_auth_bytes(live_auth)
            previous_current = self.config.current_account
            if previous_current:
                current = self._find(previous_current)
                live_info = self._read_account(home)
                if self._email_from(live_info).casefold() != current.email.casefold():
                    raise AccountServiceError("活动登录与当前账号不一致，请先添加当前账号再继续")
                # 先保存可能已经轮换的 Token，确认快照落盘后才移走活动认证。
                original_auth = self._read_auth_bytes(live_auth)
                self._atomic_write_bytes(self._snapshot_path(current), original_auth)
            else:
                # currentAccount 为空通常表示正在添加流程中，禁止误删尚未导入的新登录。
                raise AccountServiceError("当前登录尚未添加，请先点击“添加当前账号”保存后再继续")

            try:
                live_auth.unlink()
                with self._lock:
                    self.config.current_account = None
                    self.config_service.save(self.config)
            except Exception:
                self.config.current_account = previous_current
                self._atomic_write_bytes(live_auth, original_auth)
                raise

        self.environment_service.set_home(home)
        try:
            self._launch_codex(executable, home)
        except Exception:
            # 启动失败时恢复原活动认证和当前账号，避免用户停留在意外的未登录状态。
            with self._auth_lock:
                self._atomic_write_bytes(live_auth, original_auth)
                with self._lock:
                    self.config.current_account = previous_current
                    self.config_service.save(self.config)
            raise
        self.logger.info("已准备其他账号登录 home=%s", home)
        return {"success": True, "home": str(home)}

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
        """删除非当前账号的认证快照与旧版遗留目录。"""
        with self._lock:
            if self.config.current_account == account_id:
                raise AccountServiceError("当前账号不能删除，请先切换到其他账号")
            account = self._find(account_id)
            snapshot_path = self._snapshot_path(account, migrate=False)
            account_root = (
                snapshot_path.parent
                if account.auth_path
                else Path(account.home).expanduser().resolve().parent
            )
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
        """使用共享 Home 启动当前账号的 Codex。"""
        account_id = account_id or self.config.current_account
        if not account_id:
            raise AccountServiceError("尚未选择当前账号")
        account = self._find(account_id)
        if self.config.current_account != account.id:
            raise AccountServiceError("目标账号尚未切换为当前账号")
        executable = resolve_codex_executable()
        if not executable:
            raise AccountServiceError("未找到 Codex CLI，请确认已安装 Codex；应用已自动检查 PATH、npm 全局目录和常见安装目录")
        self._launch_codex(executable, self._shared_home())
        return {"accountId": account.id}

    def _launch_codex(self, executable: str, home: Path) -> None:
        """使用指定共享 Home 启动 Codex CLI。"""
        self.logger.info("使用 Codex CLI：%s", executable)
        env = os.environ.copy()
        env["CODEX_HOME"] = str(home)
        import subprocess

        subprocess.Popen(
            [executable], env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        )

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
