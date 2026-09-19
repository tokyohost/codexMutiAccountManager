"""基于标准库线程池的后台任务管理。"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from concurrent.futures import Future, ThreadPoolExecutor


class EventHook:
    """提供轻量级的事件订阅和派发能力。"""

    def __init__(self) -> None:
        """初始化订阅列表。"""
        self._listeners: list[Callable[[str], None]] = []

    def connect(self, listener: Callable[[str], None]) -> None:
        """注册事件监听器。"""
        self._listeners.append(listener)

    def emit(self, event: str) -> None:
        """向所有监听器派发事件。"""
        for listener in tuple(self._listeners):
            listener(event)


class TaskManager:
    """使用标准库线程池执行后台任务，避免依赖 Qt。"""

    def __init__(self, logger: logging.Logger) -> None:
        """初始化线程池和任务引用。"""
        self.logger = logger
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="codex-task")
        self.task_event = EventHook()
        self._workers: dict[str, Future[Any]] = {}

    def submit(self, task_type: str, function: Callable[[], Any]) -> str:
        """提交任务并返回任务 ID。"""
        task_id = str(uuid.uuid4())
        self.task_event.emit(self._event(task_id, task_type, "started"))
        future = self.pool.submit(function)
        self._workers[task_id] = future
        future.add_done_callback(lambda completed: self._finish(task_id, task_type, completed))
        return task_id

    def shutdown(self) -> None:
        """停止线程池并等待已提交任务结束。"""
        self.pool.shutdown(wait=True, cancel_futures=True)

    def _finish(self, task_id: str, task_type: str, future: Future[Any]) -> None:
        """将任务结果转换为事件并清理任务引用。"""
        try:
            event = self._event(task_id, task_type, "completed", {"result": future.result()})
        except Exception as exc:  # 后台任务异常必须转成可消费事件
            event = self._event(
                task_id,
                task_type,
                "failed",
                {"error": str(exc), "traceback": traceback.format_exc(limit=8)},
            )
            self.logger.error("后台任务失败：%s", event)
        self.task_event.emit(event)
        self._workers.pop(task_id, None)

    @staticmethod
    def _event(
        task_id: str,
        task_type: str,
        event: str,
        extra: dict[str, Any] | None = None,
    ) -> str:
        """生成统一格式的任务事件 JSON。"""
        payload = {"event": event, "taskId": task_id, "taskType": task_type}
        payload.update(extra or {})
        return json.dumps(payload, ensure_ascii=False)
