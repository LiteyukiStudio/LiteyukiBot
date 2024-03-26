from importlib.metadata import PackageNotFoundError, version
from urllib.parse import quote


def convert_size(size: int, precision: int = 2, add_unit: bool = True, suffix: str = "iB") -> str:
    """把字节数转换为人类可读的字符串，计算正负

    Args:

        add_unit:  是否添加单位，False后则suffix无效
        suffix: iB或B
        precision: 浮点数的小数点位数
        size (int): 字节数

    Returns:

        str: The human-readable string, e.g. "1.23 GB".
    """
    is_negative = False
    if size < 0:
        is_negative = True
        size = -size

    for unit in ["", "K", "M", "G", "T", "P", "E", "Z", "Y"]:
        if size < 1024:
            if add_unit:
                result = f"{size:.{precision}f} {unit}" + suffix
                return f"-{result}" if is_negative else result
            else:
                return f"{size:.{precision}f}"
        size /= 1024
    if add_unit:
        return f"{size:.{precision}f} Y" + suffix
    else:
        return f"{size:.{precision}f}"


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
