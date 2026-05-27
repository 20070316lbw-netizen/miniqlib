# -*- coding: utf-8 -*-
"""
Centralized Logging Configuration for MiniQLib.
MiniQLib 集中式日志配置模块。

Provides a uniform get_logger() interface and a configurable root logger setup,
replacing scattered print() calls with structured, level-aware logging.
提供统一的 get_logger() 接口和可配置的根 logger 设置，
用结构化、分级的日志替代分散的 print() 调用。
"""
import logging
import sys
from pathlib import Path
from typing import Optional

# 默认日志格式：时间 | 级别 | 模块名 | 消息
# Default log format: timestamp | level | module name | message
LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-7s | %(name)-24s | %(message)s"
)
LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

# 根 logger 是否已初始化 / Whether root logger has been initialized
_root_configured: bool = False


def configure_root(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    stream: bool = True,
) -> None:
    """
    配置根 logger 的全局输出级别、格式和处理器。
    Configure the root logger's global output level, format, and handlers.

    Parameters
    ----------
    level : int
        Python logging level (e.g., logging.DEBUG, logging.INFO).
        Python 日志级别（如 logging.DEBUG、logging.INFO）。
    log_file : Path, optional
        可选的日志文件路径；若提供则同时输出到 file。
        Optional log file path; if provided, also write to file.
    stream : bool, default True
        是否输出到 stderr / Whether to output to stderr.
    """
    global _root_configured

    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler / Avoid duplicate handlers
    if _root_configured:
        root.handlers.clear()

    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    if stream:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    _root_configured = True


def get_logger(name: str) -> logging.Logger:
    """
    获取或创建指定名称的模块级 logger。
    Get or create a module-level logger with the given name.

    使用惯例 / Usage convention:
        from mini_qlib.utils.log import get_logger
        _log = get_logger(__name__)

    Parameters
    ----------
    name : str
        Logger 名称，通常传入 __name__ / Logger name, typically __name__.

    Returns
    -------
    logging.Logger
        配置好的 logger 实例 / Configured logger instance.
    """
    global _root_configured
    if not _root_configured:
        configure_root()
    return logging.getLogger(name)


class PrintToLogAdapter:
    """
    将 logging 输出同时镜像到 stdout，保持与原有 print() 行为一致的终端体验。
    Mirror logging output to stdout to maintain consistent terminal experience.
    """
    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
    
    def write(self, message: str) -> None:
        if message.strip():
            self.logger.log(self.level, message.rstrip())
    
    def flush(self) -> None:
        pass
