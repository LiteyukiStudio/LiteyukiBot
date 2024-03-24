import sys
import logging
from typing import TYPE_CHECKING
from .language import get_default_lang
import loguru

if TYPE_CHECKING:
    from loguru import Logger, Record

logger: "Logger" = loguru.logger


class LoguruHandler(logging.Handler):  # pragma: no cover
    """logging 与 loguru 之间的桥梁，将 logging 的日志转发到 loguru。"""

    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def default_filter(record: "Record"):
    """默认的日志过滤器，根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("nonebot_log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level
    return record["level"].no >= levelno


default_format: str = (
        "<c>{time:YYYY-MM-DD}</c> <blue>{time:HH:mm:ss}</blue> "
        "<lvl>[{level.icon}]</lvl> "
        "<c><{name}></c> "
        "{message}"
)
"""默认日志格式"""

logger.remove()
logger_id = logger.add(
    sys.stdout,
    level=0,
    diagnose=False,
    filter=default_filter,
    format=default_format,
)
slang = get_default_lang()
logger.level("DEBUG", color="<blue>", icon=f"*️⃣ DDDEBUG")
logger.level("INFO", color="<white>", icon=f"ℹ️ IIIINFO")
logger.level("SUCCESS", color="<green>", icon=f"✅ SUCCESS")
logger.level("WARNING", color="<yellow>", icon=f"⚠️ WARNING")
logger.level("ERROR", color="<red>", icon=f"⭕ EEERROR")

"""默认日志处理器 id"""

__autodoc__ = {
        "logger_id": False
}
