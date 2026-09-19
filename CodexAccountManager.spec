# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 构建配置。"""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


project_root = Path(SPECPATH)
application_entry = project_root / "backend" / "main.py"
frontend_dist = project_root / "frontend" / "dist"
resources = project_root / "resources"
icon_path = resources / "app.ico"
version_path = project_root / "version_info.txt"
datas = []
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend/dist"))
if resources.exists():
    datas.append((str(resources), "resources"))
datas += collect_data_files("webview")
hiddenimports = ["pystray._win32", "PIL.Image"] + collect_submodules("webview")

a = Analysis(
    [str(application_entry)],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)


def should_keep_binary(entry):
    """过滤当前 Windows x64 应用不会使用的可选二进制组件。"""
    destination = entry[0].replace("\\", "/").lower()
    if destination.startswith("pil/"):
        return Path(destination).name.startswith("_imaging.cp")
    return True


a.binaries = [entry for entry in a.binaries if should_keep_binary(entry)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    name="CodexAccountManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(icon_path) if icon_path.exists() else None,
    version=str(version_path) if version_path.exists() else None,
    exclude_binaries=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CodexAccountManager",
)
