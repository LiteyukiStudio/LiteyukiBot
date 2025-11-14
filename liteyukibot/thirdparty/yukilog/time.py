from time import localtime, strftime


def get_time(time_format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """获取当前时间"""
    return strftime(time_format, localtime())

def get_date() -> str:
    """获取当前日期，格式为 %Y-%m-%d"""
    return get_time("%Y-%m-%d")

def get_time_with_ms() -> str:
    """获取当前毫秒级时间，格式为 %H:%M:%S.%f"""
    return get_time("%H:%M:%S.%f")
