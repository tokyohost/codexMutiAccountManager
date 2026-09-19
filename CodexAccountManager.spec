# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir 构建配置。"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH)
frontend_dist = project_root / "frontend" / "dist"
resources = project_root / "resources"
icon_path = resources / "app.ico"
version_path = project_root / "version_info.txt"
datas = []
if frontend_dist.exists():
    datas.append((str(frontend_dist), "frontend/dist"))
if resources.exists():
    datas.append((str(resources), "resources"))
datas += collect_data_files("PySide6")
hiddenimports = [
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebChannel",
]

a = Analysis(
    [str(project_root / "main.py")],
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
