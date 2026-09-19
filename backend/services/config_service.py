"""配置文件加载与原子保存服务。"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from threading import RLock

from backend.models.config import AppConfig
from backend.utils.paths import config_path


class ConfigService:
    """负责配置文件的容错加载和原子写入。"""

    def __init__(self, path: Path | None = None) -> None:
        """初始化配置服务。"""
        self.path = path or config_path()
        self._lock = RLock()
        self.load_error: str | None = None

    def load(self) -> AppConfig:
        """读取配置，损坏时备份原文件并返回默认配置。"""
        with self._lock:
            if not self.path.exists():
                return AppConfig()
            try:
                with self.path.open("r", encoding="utf-8-sig") as stream:
                    value = json.load(stream)
                if not isinstance(value, dict):
                    raise ValueError("配置根节点必须是对象")
                return AppConfig.from_dict(value)
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.load_error = f"配置文件损坏，已重新生成：{exc}"
                backup = self.path.with_name(
                    f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}"
                )
                try:
                    shutil.copy2(self.path, backup)
                except OSError:
                    pass
                return AppConfig()

    def save(self, config: AppConfig) -> None:
        """通过临时文件、flush 和 os.replace 原子保存配置。"""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            data = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)

