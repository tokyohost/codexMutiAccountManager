"""应用单实例保护。"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstanceGuard(QObject):
    """使用 QLocalServer 保证同一用户只运行一个实例。"""

    activateRequested = Signal()

    def __init__(self, name: str) -> None:
        """保存本地服务器名称。"""
        super().__init__()
        self.name = name
        self.server = QLocalServer(self)

    def acquire(self) -> bool:
        """尝试获取实例；已有实例时请求其显示窗口并返回 False。"""
        if self.server.listen(self.name):
            self.server.newConnection.connect(self._on_connection)
            return True
        socket = QLocalSocket()
        socket.connectToServer(self.name)
        if socket.waitForConnected(500):
            socket.write(b"show\n")
            socket.flush()
            socket.waitForBytesWritten(200)
            socket.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        return self.server.listen(self.name)

    def _on_connection(self) -> None:
        """处理第二实例发送的显示请求。"""
        socket = self.server.nextPendingConnection()
        if socket:
            socket.waitForReadyRead(200)
            self.activateRequested.emit()
            socket.disconnectFromServer()

