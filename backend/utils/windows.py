"""Windows 相关辅助函数。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def hidden_process_flags() -> int:
    """返回 Windows 下隐藏子进程窗口的创建标志。"""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0


def open_path(path: str | Path) -> None:
    """使用系统默认程序打开文件或目录。"""
    target = str(path)
    if sys.platform == "win32":
        os.startfile(target)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", target])
    else:
        subprocess.Popen(["xdg-open", target])
