import sys
import loguru
from typing import TYPE_CHECKING
from .config import config, load_from_yaml

logger = loguru.logger
if TYPE_CHECKING:
    # avoid sphinx autodoc resolve annotation failed
    # because loguru module do not have `Logger` class actually
    from loguru import Logger, Record


def default_filter(record: "Record"):
    """默认的日志过滤器，根据 `config.log_level` 配置改变日志等级。"""
    log_level = record["extra"].get("nonebot_log_level", "INFO")
    levelno = logger.level(log_level).no if isinstance(log_level, str) else log_level
    return record["level"].no >= levelno


# DEBUG日志格式
debug_format: str = (
        "<c>{time:YYYY-MM-DD}</c> <blue>{time:HH:mm:ss}</blue> "
        "<lvl>[{level.icon}]</lvl> "
        "<c><{name}.{module}.{function}:{line}></c> "
        "{message}"
)

# 默认日志格式
default_format: str = (
        "<c>{time:MM-DD}</c> <blue>{time:HH:mm:ss}</blue> "
        "<lvl>[{level.icon}]</lvl> "
        "<c><{name}></c> "
        "{message}"
)


def get_format(level: str) -> str:
    if level == "DEBUG":
        return debug_format
    else:
        return default_format


logger = loguru.logger.bind(get_format=get_format)

logger.remove()
logger_id = logger.add(
    sys.stdout,
    level=0,
    diagnose=False,
    filter=default_filter,
    format=get_format(load_from_yaml('config.yml').get("log_level", "INFO")),
)


logger.level("DEBUG", color="<blue>", icon=f"*️⃣==DEBUG")
logger.level("INFO", color="<white>", icon=f"ℹ️===INFO")
logger.level("SUCCESS", color="<green>", icon=f"✅SUCCESS")
logger.level("WARNING", color="<yellow>", icon=f"⚠️WARNING")
logger.level("ERROR", color="<red>", icon=f"⭕==ERROR")
