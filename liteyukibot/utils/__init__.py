import json
from typing import Any


def pretty_print(obj: Any, indent: int=2) -> None:
    """
    更好地打印对象

    Args:
        obj (Any): 要打印的对象
    """
    print(json.dumps(obj, indent=indent, ensure_ascii=False))
    
def pretty_format(obj: Any, indent: int =2 ) -> str:
    """
    更好地格式化对象

    Args:
        obj (Any): 要格式化的对象

    Returns:
        str: 格式化后的字符串
    """
    return json.dumps(obj, indent=indent, ensure_ascii=False)