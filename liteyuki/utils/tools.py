import random
from importlib.metadata import PackageNotFoundError, version


def clamp(value: float, min_value: float, max_value: float) -> float | int:
    """将值限制在最小值和最大值之间

    Args:
        value (float): 要限制的值
        min_value (float): 最小值
        max_value (float): 最大值

    Returns:
        float: 限制后的值
    """
    return max(min(value, max_value), min_value)


def convert_size(size: int, precision: int = 2, add_unit: bool = True, suffix: str = " XiB") -> str | float:
    """把字节数转换为人类可读的字符串，计算正负

    Args:

        add_unit:  是否添加单位，False后则suffix无效
        suffix: XiB或XB
        precision: 浮点数的小数点位数
        size (int): 字节数

    Returns:

        str: The human-readable string, e.g. "1.23 GB".
    """
    is_negative = size < 0
    size = abs(size)
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if size < 1024:
            break
        size /= 1024
    if is_negative:
        size = -size
    if add_unit:
        return f"{size:.{precision}f}{suffix.replace('X', unit)}"
    else:
        return size


def keywords_in_text(keywords: list[str], text: str, all_matched: bool) -> bool:
    """
    检查关键词是否在文本中
    Args:
        keywords: 关键词列表
        text: 文本
        all_matched: 是否需要全部匹配

    Returns:

    """
    if all_matched:
        for keyword in keywords:
            if keyword not in text:
                return False
        return True
    else:
        for keyword in keywords:
            if keyword in text:
                return True
        return False


def check_for_package(package_name: str) -> bool:
    try:
        version(package_name)
        return True
    except PackageNotFoundError:
        return False


def random_ascii_string(length: int) -> str:
    """
    生成随机ASCII字符串
    Args:
        length:

    Returns:

    """
    return "".join([chr(random.randint(33, 126)) for _ in range(length)])


def random_hex_string(length: int) -> str:
    """
    生成随机十六进制字符串
    Args:
        length:

    Returns:

    """
    return "".join([random.choice("0123456789abcdef") for _ in range(length)])
