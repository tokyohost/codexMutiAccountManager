import json
import logging
from pathlib import Path

import pytest

import backend.services.account_service as account_service_module
from backend.services.account_service import AccountService, AccountServiceError
from backend.services.config_service import ConfigService


class StubEnvironmentService:
    """为账号服务测试提供固定的共享 CODEX_HOME。"""

    def __init__(self, home: Path) -> None:
        """保存测试 Home。"""
        self.home = home

    def get_current_home(self) -> Path:
        """返回测试 Home。"""
        return self.home

    def set_home(self, home: Path) -> None:
        """记录切换后继续使用的共享 Home。"""
        self.home = Path(home)


class StubProcessService:
    """模拟没有运行中 Codex 的进程服务。"""

    @staticmethod
    def find_codex_processes() -> list[object]:
        """返回空进程列表。"""
        return []

    @staticmethod
    def close_codex() -> bool:
        """模拟成功关闭 Codex。"""
        return True


def build_service(tmp_path: Path, source_home: Path, monkeypatch: pytest.MonkeyPatch) -> AccountService:
    """构造目录完全隔离的账号服务。"""
    managed_root = tmp_path / "managed"
    monkeypatch.setattr(account_service_module, "accounts_dir", lambda: managed_root)
    return AccountService(
        ConfigService(tmp_path / "config.json"),
        StubEnvironmentService(source_home),
        StubProcessService(),
        logging.getLogger("test-account-service"),
    )


def write_auth(home: Path, email: str, generation: int = 1) -> None:
    """写入不含真实凭据的测试认证文件。"""
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text(
        json.dumps({"email": email, "generation": generation}), encoding="utf-8"
    )


def fake_read_account(home: Path) -> dict[str, str]:
    """从测试认证文件提取邮箱，模拟 account/read。"""
    value = json.loads((Path(home) / "auth.json").read_text(encoding="utf-8"))
    return {"email": str(value["email"]), "planType": "plus"}


def test_import_only_saves_auth_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """导入只应保存认证快照，不复制共享 Home 中的其他内容。"""
    source_home = tmp_path / "source"
    write_auth(source_home, "user@example.com")
    (source_home / "sessions").mkdir()
    (source_home / "sessions" / "history.jsonl").write_text("记录", encoding="utf-8")
    (source_home / "state.sqlite-wal").write_text("volatile", encoding="utf-8")
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(service, "_read_account", fake_read_account)

    result = service.import_current_account()

    account = service.config.accounts[0]
    snapshot_path = Path(account.auth_path)
    assert result["accountId"] == account.id
    assert result["suggestSwitch"] is False
    assert service.config.current_account == account.id
    assert service.config.shared_home == str(source_home.resolve())
    assert account.home == str(source_home.resolve())
    assert json.loads(snapshot_path.read_text(encoding="utf-8"))["email"] == "user@example.com"
    assert not (snapshot_path.parent / "sessions").exists()
    assert not (snapshot_path.parent / "state.sqlite-wal").exists()
    loaded = ConfigService(tmp_path / "config.json").load()
    assert loaded.accounts[0].auth_path == str(snapshot_path)


def test_switch_syncs_rotated_auth_and_replaces_live_auth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """切换前应保存当前账号的新 Token 代次，再激活目标快照。"""
    source_home = tmp_path / "source"
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(service, "_read_account", fake_read_account)

    write_auth(source_home, "first@example.com")
    first_id = str(service.import_current_account()["accountId"])
    write_auth(source_home, "second@example.com")
    second_id = str(service.import_current_account()["accountId"])
    write_auth(source_home, "second@example.com", generation=2)

    result = service.switch_account(first_id)

    first = service._find(first_id)
    second = service._find(second_id)
    live = json.loads((source_home / "auth.json").read_text(encoding="utf-8"))
    saved_second = json.loads(Path(second.auth_path).read_text(encoding="utf-8"))
    assert result["success"] is True
    assert service.config.current_account == first.id
    assert live["email"] == "first@example.com"
    assert saved_second["generation"] == 2


def test_switch_restores_original_auth_when_verification_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """目标账号验证失败时应恢复原认证文件和当前账号标记。"""
    source_home = tmp_path / "source"
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(service, "_read_account", fake_read_account)
    write_auth(source_home, "first@example.com")
    first_id = str(service.import_current_account()["accountId"])
    write_auth(source_home, "second@example.com")
    second_id = str(service.import_current_account()["accountId"])

    def reject_first_on_live_home(home: Path) -> dict[str, str]:
        """仅在目标快照写入活动 Home 后模拟邮箱验证不一致。"""
        info = fake_read_account(home)
        if Path(home).resolve() == source_home.resolve() and info["email"] == "first@example.com":
            return {"email": "unexpected@example.com"}
        return info

    monkeypatch.setattr(service, "_read_account", reject_first_on_live_home)
    with pytest.raises(AccountServiceError, match="邮箱不一致"):
        service.switch_account(first_id)

    restored = json.loads((source_home / "auth.json").read_text(encoding="utf-8"))
    assert restored["email"] == "second@example.com"
    assert service.config.current_account == second_id


def test_import_rejects_concurrent_request(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """已有导入执行时，后续请求应立即得到可理解的错误。"""
    source_home = tmp_path / "source"
    source_home.mkdir()
    service = build_service(tmp_path, source_home, monkeypatch)
    service._import_lock.acquire()
    try:
        with pytest.raises(AccountServiceError, match="正在导入"):
            service.import_current_account()
    finally:
        service._import_lock.release()


def test_prepare_other_login_preserves_snapshot_without_logout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """登录其他账号前应保存最新认证、移走活动文件且不调用服务端注销。"""
    source_home = tmp_path / "source"
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(service, "_read_account", fake_read_account)
    monkeypatch.setattr(account_service_module, "resolve_codex_executable", lambda: "codex.exe")
    launched: list[tuple[str, Path]] = []
    monkeypatch.setattr(
        service, "_launch_codex", lambda executable, home: launched.append((executable, home))
    )
    write_auth(source_home, "user@example.com")
    account_id = str(service.import_current_account()["accountId"])
    write_auth(source_home, "user@example.com", generation=2)

    result = service.prepare_other_account_login()

    snapshot = json.loads(Path(service._find(account_id).auth_path).read_text(encoding="utf-8"))
    assert result["success"] is True
    assert snapshot["generation"] == 2
    assert not (source_home / "auth.json").exists()
    assert service.config.current_account is None
    assert launched == [("codex.exe", source_home.resolve())]


def test_prepare_other_login_rejects_unmanaged_active_login(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """添加流程中出现尚未保存的新登录时，不得直接删除其认证文件。"""
    source_home = tmp_path / "source"
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(account_service_module, "resolve_codex_executable", lambda: "codex.exe")
    write_auth(source_home, "new@example.com")

    with pytest.raises(AccountServiceError, match="尚未添加"):
        service.prepare_other_account_login()

    assert (source_home / "auth.json").is_file()


def test_prepare_other_login_restores_auth_when_launch_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未登录 Codex 启动失败时应恢复活动认证和当前账号标记。"""
    source_home = tmp_path / "source"
    service = build_service(tmp_path, source_home, monkeypatch)
    monkeypatch.setattr(service, "_read_account", fake_read_account)
    monkeypatch.setattr(account_service_module, "resolve_codex_executable", lambda: "codex.exe")
    monkeypatch.setattr(
        service,
        "_launch_codex",
        lambda executable, home: (_ for _ in ()).throw(OSError("launch failed")),
    )
    write_auth(source_home, "user@example.com")
    account_id = str(service.import_current_account()["accountId"])

    with pytest.raises(OSError, match="launch failed"):
        service.prepare_other_account_login()

    assert (source_home / "auth.json").is_file()
    assert service.config.current_account == account_id
