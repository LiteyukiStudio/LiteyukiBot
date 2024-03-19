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


def de_escape(text: str) -> str:
    str_map = {
        "&#91;": "[",
        "&#93;": "]",
        "&amp;": "&",
        "&#44;": ",",
    }
    for k, v in str_map.items():
        text = text.replace(k, v)

    return text
