import nonebot


def convert_duration(text: str, default) -> float:
    """
    转换自然语言时间为秒数
    Args:
        text: 1d2h3m
        default: 出错时返回

    Returns:
        float: 总秒数
    """
    units = {
            "d" : 86400,
            "h" : 3600,
            "m" : 60,
            "s" : 1,
            "ms": 0.001
    }

    duration = 0
    current_number = ''
    current_unit = ''
    try:
        for char in text:
            if char.isdigit():
                current_number += char
            else:
                if current_number:
                    duration += int(current_number) * units[current_unit]
                    current_number = ''
                if char in units:
                    current_unit = char
                else:
                    current_unit = ''

        if current_number:
            duration += int(current_number) * units[current_unit]

        return duration

    except BaseException as e:
        nonebot.logger.info(f"convert_duration error: {e}")
        return default


def convert_time_to_seconds(time_str):
    """转换自然语言时长为秒数
    Args:
        time_str: 1d2m3s

    Returns:

    """
    seconds = 0
    current_number = ''

    for char in time_str:
        if char.isdigit() or char == '.':
            current_number += char
        elif char == 'd':
            seconds += float(current_number) * 24 * 60 * 60
            current_number = ''
        elif char == 'h':
            seconds += float(current_number) * 60 * 60
            current_number = ''
        elif char == 'm':
            seconds += float(current_number) * 60
            current_number = ''
        elif char == 's':
            seconds += float(current_number)
            current_number = ''

    return int(seconds)


def convert_seconds_to_time(seconds):
    """转换秒数为自然语言时长
    Args:
        seconds: 10000

    Returns:

    """
    d = seconds // (24 * 60 * 60)
    h = (seconds % (24 * 60 * 60)) // (60 * 60)
    m = (seconds % (60 * 60)) // 60
    s = seconds % 60

    # 若值为0则不显示
    time_str = ''
    if d:
        time_str += f"{d}d"
    if h:
        time_str += f"{h}h"
    if m:
        time_str += f"{m}m"
    if not time_str:
        time_str = f"{s}s"
    return time_str
