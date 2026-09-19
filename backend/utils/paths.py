"""应用目录路径工具。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DATA_NAME = "CodexAccountManager"


def app_data_dir() -> Path:
    """返回应用的本地数据目录。"""
    root = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    path = Path(root) / APP_DATA_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    """返回配置文件路径。"""
    return app_data_dir() / "config.json"


def accounts_dir() -> Path:
    """返回受管账号目录。"""
    path = app_data_dir() / "accounts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    """返回日志目录。"""
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def frontend_index_path() -> Path:
    """返回生产环境前端入口，兼容源码运行和 PyInstaller 目录运行。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "frontend" / "dist" / "index.html"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist" / "index.html"


def resources_dir() -> Path:
    """返回应用资源目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "resources"
    return Path(__file__).resolve().parents[2] / "resources"

