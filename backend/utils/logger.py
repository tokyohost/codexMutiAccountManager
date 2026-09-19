"""日志配置与敏感信息脱敏。"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from backend.utils.paths import logs_dir


_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)((?:bearer\s+)?[^\s,;]+)"),
    re.compile(r"(?i)(bearer\s+)([^\s,;]+)"),
    re.compile(r'(?i)("(?:accessToken|refreshToken|token|apiKey)"\s*:\s*")([^"]+)(")'),
    re.compile(r"(?i)((?:access_token|refresh_token|api_key|jwt)\s*[:=]\s*)([^\s,;]+)"),
)


def redact(text: object) -> str:
    """移除日志文本中的常见令牌和授权头。"""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 3:
            value = pattern.sub(r"\1***\3", value)
        else:
            value = pattern.sub(r"\1***", value)
    return value


class RedactingFormatter(logging.Formatter):
    """对日志消息统一脱敏的格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化并脱敏一条日志。"""
        return redact(super().format(record))


def configure_logging() -> logging.Logger:
    """创建应用滚动日志记录器。"""
    logger = logging.getLogger("codex_account_manager")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        logs_dir() / "app.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(RedactingFormatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)
    return logger
