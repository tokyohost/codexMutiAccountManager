"""Codex CLI 可执行文件定位工具。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from backend.utils.windows import hidden_process_flags


_CODEX_NAMES = ("codex.exe", "codex.cmd", "codex.bat", "codex")


def resolve_codex_executable() -> str | None:
    """按优先级定位 Codex CLI，兼容未加入 PATH 的 npm 全局安装。"""
    candidates: list[Path] = []
    configured = os.environ.get("CODEX_EXECUTABLE", "").strip().strip('"')
    if configured:
        candidates.append(Path(configured).expanduser())

    path_command = shutil.which("codex")
    if path_command:
        candidates.append(Path(path_command))

    found = _first_existing(candidates + _common_install_paths() + _registry_paths())
    if found:
        return found
    found = _first_existing(_npm_global_paths())
    if found:
        return found
    return None


def _common_install_paths() -> list[Path]:
    """返回 Codex Desktop、npm 和用户 bin 目录中的常见路径。"""
    home = Path.home()
    app_data = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    local_app_data = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    bases = [
        app_data / "npm",
        local_app_data / "npm",
        home / ".npm-global" / "bin",
        home / ".local" / "bin",
        local_app_data / "OpenAI" / "Codex",
        local_app_data / "OpenAI" / "Codex" / "bin",
        local_app_data / "Programs" / "Codex",
        local_app_data / "Programs" / "Codex" / "bin",
        local_app_data / "Codex",
        local_app_data / "Codex" / "bin",
        program_files / "Codex",
        program_files / "Codex" / "bin",
        program_files_x86 / "Codex",
        program_files_x86 / "Codex" / "bin",
    ]
    paths = [base / name for base in bases for name in _CODEX_NAMES]
    versioned_bin = local_app_data / "OpenAI" / "Codex" / "bin"
    try:
        version_dirs = [item for item in versioned_bin.iterdir() if item.is_dir()]
    except OSError:
        version_dirs = []
    paths.extend(version_dir / name for version_dir in version_dirs for name in _CODEX_NAMES)
    return paths


def _npm_global_paths() -> list[Path]:
    """通过本机 npm prefix 补充自定义全局安装目录。"""
    npm_commands: list[str] = []
    npm_path = shutil.which("npm")
    if npm_path:
        npm_commands.append(npm_path)
    for candidate in (
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "nodejs" / "npm.cmd",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        / "Programs"
        / "nodejs"
        / "npm.cmd",
    ):
        if candidate.is_file():
            npm_commands.append(str(candidate))

    result: list[Path] = []
    for npm in dict.fromkeys(npm_commands):
        try:
            completed = subprocess.run(
                [npm, "prefix", "-g"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=3,
                creationflags=hidden_process_flags(),
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        prefix = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
        if prefix:
            prefix_path = Path(prefix.strip().strip('"'))
            result.extend(prefix_path / name for name in _CODEX_NAMES)
            result.extend((prefix_path / "bin") / name for name in _CODEX_NAMES)
    return result


def _registry_paths() -> list[Path]:
    """读取 Windows App Paths 注册表中的 Codex 安装位置。"""
    if os.name != "nt":
        return []
    import winreg

    result: list[Path] = []
    locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\codex.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\codex.exe"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\codex.exe"),
    )
    for hive, key_path in locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                value, _ = winreg.QueryValueEx(key, None)
        except (FileNotFoundError, OSError):
            continue
        if value:
            result.append(Path(str(value).strip().strip('"')))
    return result


def _unique_paths(paths: list[Path]) -> list[Path]:
    """按不区分大小写的绝对路径去重。"""
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            normalized = os.path.normcase(str(path.expanduser().resolve()))
        except OSError:
            normalized = os.path.normcase(str(path.expanduser()))
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(path)
    return result


def _first_existing(paths: list[Path]) -> str | None:
    """返回候选列表中的第一个可执行文件。"""
    for candidate in _unique_paths(paths):
        if candidate.is_file() and candidate.name.lower().startswith("codex"):
            return str(candidate)
    return None
