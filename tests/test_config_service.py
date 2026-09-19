from pathlib import Path

from backend.models.account import Account
from backend.models.config import AppConfig
from backend.services.config_service import ConfigService


def test_config_is_written_as_utf8_without_bom(tmp_path: Path) -> None:
    service = ConfigService(tmp_path / "config.json")
    config = AppConfig(accounts=[Account(id="a", name="个人 Plus", email="a@example.com")])
    service.save(config)
    raw = (tmp_path / "config.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    loaded = service.load()
    assert loaded.accounts[0].name == "个人 Plus"


def test_corrupt_config_is_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{broken", encoding="utf-8")
    service = ConfigService(path)
    assert service.load().accounts == []
    assert service.load_error
    assert list(tmp_path.glob("config.corrupt-*.json"))
