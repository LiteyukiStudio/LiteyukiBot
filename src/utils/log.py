import sys
import logging
from typing import TYPE_CHECKING

import loguru

if TYPE_CHECKING:
    # avoid sphinx autodoc resolve annotation failed
    # because loguru module do not have `Logger` class actually
    from loguru import Logger, Record

# logger = logging.getLogger("nonebot")
logger: "Logger" = loguru.logger
"""NoneBot 日志记录器对象。

默认信息:

- 格式: `[%(asctime)s %(name)s] %(levelname)s: %(message)s`
- 等级: `INFO` ，根据 `config.log_level` 配置改变
- 输出: 输出至 stdout

用法:
    ```python
    from nonebot.log import logger
    ```
"""


# default_handler = logging.StreamHandler(sys.stdout)
# default_handler.setFormatter(
#     logging.Formatter("[%(asctime)s %(name)s] %(levelname)s: %(message)s"))
# logger.addHandler(default_handler)


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
        "<g>{time:MM-DD HH:mm:ss}</g> "
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

logger.level("DEBUG", color="<cyan>", icon="㊙️DEBU")
logger.level("INFO", color="<white>", icon="ℹ️INFO")
logger.level("SUCCESS", color="<green>", icon="✅SUCC")
logger.level("WARNING", color="<yellow>", icon="⚠️WARN")
logger.level("ERROR", color="<red>", icon="☢️ERRO")

"""默认日志处理器 id"""

__autodoc__ = {
        "logger_id": False
}
