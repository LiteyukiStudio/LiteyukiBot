"""
Module docs
"""
from typing import TypeAlias


class Nil():
    def __eq__(self, other):
        if isinstance(other, Nil):
            return True
        return other is None

    # 不等于
    def __ne__(self, other):
        return not self.__eq__(other)


nil = Nil()

err: TypeAlias = Exception | Nil