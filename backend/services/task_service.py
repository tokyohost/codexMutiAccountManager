"""Qt 线程池任务管理。"""

from __future__ import annotations

import json
import logging
import traceback
import uuid
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    """后台任务向 Qt 主线程传递事件的信号集合。"""

    started = Signal(str)
    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)


class TaskWorker(QRunnable):
    """在线程池中执行一个可调用对象。"""

    def __init__(self, task_id: str, task_type: str, function: Callable[[], Any]) -> None:
        """保存任务信息。"""
        super().__init__()
        self.task_id = task_id
        self.task_type = task_type
        self.function = function
        self.signals = WorkerSignals()

    def run(self) -> None:
        """执行任务并将结果包装成统一 JSON 事件。"""
        self.signals.started.emit(self._event("started"))
        try:
            result = self.function()
            self.signals.completed.emit(self._event("completed", {"result": result}))
        except Exception as exc:  # 后台任务必须转为事件，不能杀死 GUI 进程
            self.signals.failed.emit(
                self._event(
                    "failed",
                    {"error": str(exc), "traceback": traceback.format_exc(limit=8)},
                )
            )

    def _event(self, event: str, extra: dict[str, Any] | None = None) -> str:
        """生成任务事件 JSON。"""
        payload = {"event": event, "taskId": self.task_id, "taskType": self.task_type}
        payload.update(extra or {})
        return json.dumps(payload, ensure_ascii=False)


class TaskManager(QObject):
    """统一使用 QThreadPool 管理耗时任务。"""

    task_event = Signal(str)

    def __init__(self, logger: logging.Logger) -> None:
        """初始化线程池并保留任务引用。"""
        super().__init__()
        self.logger = logger
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, min(4, self.pool.maxThreadCount())))
        self._workers: dict[str, TaskWorker] = {}

    def submit(self, task_type: str, function: Callable[[], Any]) -> str:
        """提交任务并返回任务 ID。"""
        task_id = str(uuid.uuid4())
        worker = TaskWorker(task_id, task_type, function)
        worker.signals.started.connect(self.task_event)
        worker.signals.progress.connect(self.task_event)
        worker.signals.completed.connect(self._on_completed)
        worker.signals.failed.connect(self._on_failed)
        self._workers[task_id] = worker
        self.pool.start(worker)
        return task_id

    def _on_completed(self, event: str) -> None:
        """转发成功事件并清理任务引用。"""
        self.task_event.emit(event)
        self._cleanup(event)

    def _on_failed(self, event: str) -> None:
        """记录并转发失败事件。"""
        self.logger.error("后台任务失败：%s", event)
        self.task_event.emit(event)
        self._cleanup(event)

    def _cleanup(self, event: str) -> None:
        """根据事件中的任务 ID 清理工作对象。"""
        try:
            task_id = json.loads(event)["taskId"]
        except (KeyError, TypeError, json.JSONDecodeError):
            return
        self._workers.pop(task_id, None)

