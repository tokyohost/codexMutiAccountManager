"""Codex 进程检测与关闭服务。"""

from __future__ import annotations

import logging
import time

import psutil


class ProcessService:
    """只处理明确属于 Codex 的进程，避免误杀开发工具。"""

    _EXACT_NAMES = {"codex.exe", "codex"}

    def __init__(self, logger: logging.Logger) -> None:
        """初始化进程服务。"""
        self.logger = logger

    def find_codex_processes(self) -> list[psutil.Process]:
        """查找 Codex Desktop、CLI 及 app-server 进程。"""
        result: list[psutil.Process] = []
        current_pid = psutil.Process().pid
        for process in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                if process.info["pid"] == current_pid:
                    continue
                name = (process.info.get("name") or "").lower()
                command = " ".join(process.info.get("cmdline") or []).lower()
                if name in self._EXACT_NAMES or "codex app-server" in command:
                    result.append(process)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return result

    def close_codex(self, timeout: float = 8.0) -> bool:
        """优雅终止 Codex，超时后强制结束。"""
        processes = self.find_codex_processes()
        if not processes:
            return True
        for process in processes:
            try:
                self.logger.info("准备关闭 Codex 进程 pid=%s", process.pid)
                process.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                self.logger.warning("关闭 Codex 进程失败 pid=%s: %s", process.pid, exc)
        _, alive = psutil.wait_procs(processes, timeout=timeout)
        for process in alive:
            try:
                process.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if alive:
            time.sleep(0.2)
        return all(not process.is_running() for process in alive)

