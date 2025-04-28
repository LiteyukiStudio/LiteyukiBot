import inspect
import logging
import sys

from yukilog import default_debug_and_trace_format, default_format, get_logger

logger = get_logger("INFO")

class LoguruHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = str(record.levelno)

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

# 替换 logging 的全局日志器
root_logger = logging.getLogger()
root_logger.handlers = [LoguruHandler()]  # 只保留 LoguruHandler
root_logger.setLevel(logging.INFO)


def set_level(level: str):
    """设置日志级别

    Args:
        level (str): 日志级别
    """
    logger.remove()
    logger.add(sys.stdout, format=default_format if level not in ["DEBUG", "TRACE"] else default_debug_and_trace_format, level=level)
    logging.getLogger().setLevel(level)