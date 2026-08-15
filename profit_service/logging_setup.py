# -*- coding: utf-8 -*-
"""系统日志模块

- setup_logging(): RotatingFileHandler(5MB×5, utf-8) 写 data/logs/app.log
- attach_task_id(): 用 threading.local 为当前线程绑定 task_id，格式 [task=xxx]
- 日志内容先过 security.sanitize 脱敏（security 未实现时降级为原样输出）
"""
import logging
import logging.handlers
import os
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 线程局部变量，保存当前线程的 task_id 上下文
_local = threading.local()

# 模块级单例 logger
_logger = None

_FORMAT = "[%(asctime)s][%(levelname)s][task=%(task_id)s] %(message)s"


class _TaskIdFilter(logging.Filter):
    """从线程局部变量取 task_id，未设置时显示 '-'"""

    def filter(self, record):
        record.task_id = getattr(_local, "task_id", "-")
        return True


def attach_task_id(task_id: str) -> None:
    """为当前线程绑定 task_id（仅影响本线程后续日志）"""
    _local.task_id = task_id


def _sanitize(msg: str) -> str:
    """日志脱敏；security 模块未就绪时原样返回"""
    try:
        from security import sanitize

        return sanitize(str(msg))
    except Exception:
        return str(msg)


class _SanitizeFilter(logging.Filter):
    """脱敏消息内容（Filter 每 record 只执行一次；formatter 会被 shouldRollover/emit 重复调用，勿放此处）"""

    def filter(self, record):
        record.msg = _sanitize(record.msg)
        return True


def setup_logging(log_dir="data/logs") -> logging.Logger:
    """初始化系统日志，返回 logger（幂等，重复调用返回单例）"""
    global _logger
    if _logger is not None:
        return _logger
    path = log_dir if os.path.isabs(log_dir) else os.path.join(BASE_DIR, log_dir)
    os.makedirs(path, exist_ok=True)
    logger = logging.getLogger("profit_service")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # 只写文件，避免终端乱码
    if not logger.handlers:
        handler = logging.handlers.RotatingFileHandler(
            os.path.join(path, "app.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler.addFilter(_TaskIdFilter())
        handler.addFilter(_SanitizeFilter())
        logger.addHandler(handler)
    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """返回模块级单例 logger（未初始化时自动初始化）"""
    if _logger is None:
        return setup_logging()
    return _logger
