"""Codex App Server JSON-RPC 客户端。"""

from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from typing import Any

from backend.utils.logger import redact
from backend.utils.windows import hidden_process_flags


class CodexAppServerError(RuntimeError):
    """表示 App Server 启动、通信或业务返回错误。"""


class CodexAppServerClient:
    """以一次性会话方式调用 codex app-server，避免长期占用进程。"""

    def __init__(self, home: str, logger: logging.Logger, timeout: float = 10.0) -> None:
        """记录 CODEX_HOME、日志器和单次请求超时。"""
        self.home = home
        self.logger = logger
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str] = queue.Queue()
        self._request_id = 0
        self._reader_threads: list[threading.Thread] = []

    def start(self) -> None:
        """启动 App Server 并完成 initialize。"""
        executable = os.environ.get("CODEX_EXECUTABLE") or shutil.which("codex")
        if not executable:
            raise CodexAppServerError("未找到 codex 命令，请确认 Codex 已安装并加入 PATH")
        env = os.environ.copy()
        env["CODEX_HOME"] = self.home
        try:
            self.process = subprocess.Popen(
                [executable, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=hidden_process_flags(),
            )
        except OSError as exc:
            raise CodexAppServerError(f"启动 codex app-server 失败：{exc}") from exc
        self.logger.info("App Server 已启动 home=%s", self.home)
        self._start_reader(self.process.stdout, self._responses, "stdout")
        self._start_reader(self.process.stderr, None, "stderr")
        self.request(
            "initialize",
            {
                "clientInfo": {
                    "name": "codex_account_manager",
                    "title": "Codex Account Manager",
                    "version": "1.0.0",
                }
            },
        )

    def _start_reader(self, stream: Any, output: queue.Queue[str] | None, stream_name: str) -> None:
        """启动独立读取线程，确保 stdout/stderr 管道不会互相阻塞。"""
        def read_lines() -> None:
            try:
                for line in iter(stream.readline, ""):
                    if output is not None:
                        output.put(line)
                    else:
                        self.logger.info("app-server stderr: %s", redact(line.rstrip()))
            except (OSError, ValueError) as exc:
                self.logger.debug("读取 app-server %s 结束：%s", stream_name, exc)

        thread = threading.Thread(target=read_lines, name=f"codex-{stream_name}", daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """发送 JSON-RPC 请求并等待匹配响应。"""
        if not self.process or not self.process.stdin:
            raise CodexAppServerError("App Server 尚未启动")
        self._request_id += 1
        request_id = self._request_id
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
        try:
            self.process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.process.stdin.flush()
        except (OSError, ValueError) as exc:
            raise CodexAppServerError(f"发送 App Server 请求失败：{exc}") from exc
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                line = self._responses.get(timeout=max(0.05, deadline - time.monotonic()))
            except queue.Empty as exc:
                raise CodexAppServerError(f"App Server 请求超时：{method}") from exc
            try:
                response = json.loads(line)
            except json.JSONDecodeError:
                self.logger.warning("忽略非 JSON stdout：%s", redact(line.rstrip()))
                continue
            if response.get("id") != request_id:
                self.logger.debug("忽略 App Server 通知：%s", response.get("method"))
                continue
            if response.get("error"):
                error = response["error"]
                raise CodexAppServerError(f"App Server 返回错误：{error.get('message', error)}")
            return response.get("result") or {}
        raise CodexAppServerError(f"App Server 请求超时：{method}")

    def read_account(self) -> dict[str, Any]:
        """读取当前 CODEX_HOME 的账号信息。"""
        return self.request("account/read", {"refreshToken": False})

    def read_rate_limits(self) -> dict[str, Any]:
        """读取当前 CODEX_HOME 的额度信息。"""
        return self.request("account/rateLimits/read", {})

    def close(self) -> None:
        """停止 App Server，超时后 terminate/kill。"""
        process = self.process
        if not process:
            return
        try:
            if process.poll() is None and process.stdin:
                try:
                    self.request("shutdown", {})
                except CodexAppServerError:
                    pass
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
            process.wait(timeout=2)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            try:
                process.terminate()
                process.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    process.kill()
                except OSError:
                    pass
        finally:
            self.process = None
            self.logger.info("App Server 已停止 home=%s", self.home)

    def __enter__(self) -> "CodexAppServerClient":
        """支持 with 语法启动客户端。"""
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        """离开 with 代码块时关闭客户端。"""
        self.close()

