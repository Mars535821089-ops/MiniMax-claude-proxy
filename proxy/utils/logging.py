"""统一日志配置 —— 使用 loguru，便于切级别+按文件轮转。"""
from __future__ import annotations
import sys
from pathlib import Path
from loguru import logger

_initialized = False


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    global _initialized
    if _initialized:
        return
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
               "<level>{level:<7}</level> | "
               "<cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
        backtrace=True,
        diagnose=False,
    )
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_file,
            level=level,
            rotation="50 MB",
            retention="14 days",
            compression="zip",
            enqueue=True,
        )
    _initialized = True


def get_logger(name: str | None = None):
    return logger.bind(component=name or "proxy")
