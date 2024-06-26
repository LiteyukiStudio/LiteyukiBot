"""exception模块包含了liteyuki运行中的所有错误
"""

from typing import Any, Optional


class LiteyukiException(BaseException):
    """Liteyuki的异常基类。"""
    def __str__(self) -> str:
        return self.__repr__()
