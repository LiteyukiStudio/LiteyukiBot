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

    except:
        return default
