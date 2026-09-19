"""应用单实例保护。"""

from __future__ import annotations

import ctypes
import os

from backend.services.task_service import EventHook


class SingleInstanceGuard:
    """使用 Windows 命名互斥量保证同一用户只运行一个实例。"""

    _ERROR_ALREADY_EXISTS = 183

    def __init__(self, name: str) -> None:
        """保存互斥量名称并初始化状态。"""
        self.name = name
        self.activateRequested = EventHook()
        self._mutex = None

    def acquire(self) -> bool:
        """尝试获取互斥量；已有实例时返回 False。"""
        if os.name != "nt":
            return True
        self._mutex = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        if ctypes.windll.kernel32.GetLastError() == self._ERROR_ALREADY_EXISTS:
            self.release()
            return False
        return True

    def release(self) -> None:
        """释放当前进程持有的互斥量。"""
        if self._mutex:
            ctypes.windll.kernel32.CloseHandle(self._mutex)
            self._mutex = None
