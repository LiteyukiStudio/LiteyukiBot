"""
liteyuki function是一种类似于mcfunction的函数，用于在liteyuki中实现一些功能，例如自定义指令等，也可与Python函数绑定
使用 /function function_name *args **kwargs来调用
例如 /function test/hello user_id=123456
可以用于一些轻量级插件的编写，无需Python代码
SnowyKami
"""
import functools
# cmd *args **kwargs
# api api_name **kwargs
import os
from typing import Any, Awaitable, Callable, Coroutine

from nonebot import Bot
from nonebot.adapters.satori import bot

ly_function_extensions = (
        "lyf",
        "lyfunction",
        "mcfunction"
)

loaded_functions = dict()


class LiteyukiFunction:
    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self.functions = list()

        self.bot: Bot = None

        self.var_data = dict()
        self.macro_data = dict()

    def __call__(self, *args, **kwargs):
        for _callable in self.functions:
            if _callable is not None:
                _callable(*args, **kwargs)

    def __str__(self):
        return f"LiteyukiFunction({self.name}, {self.path})"

    def __repr__(self):
        return self.__str__()

    async def execute_line(self, line: str) -> Callable[[tuple, dict], Coroutine[Any, Any, Any] | Any] | None:
        """
        解析一行轻雪函数
        Args:
            line:
        Returns:
        """

        args: list[str] = line.split(" ")
        head = args.pop(0)
        if head.startswith("#"):
            # 注释
            return None

        elif head == "var":
            # 变量定义
            for arg in args:
                self.var_data[arg.split("=", 1)[0]] = eval(arg.split("=", 1)[1])

        elif head == "cmd":
            # 在当前计算机上执行命令
            os.system(line.split(" ", 1)[1])

        elif head == "api":
            # 调用Bot API 需要Bot实例
            await self.bot.call_api(line.split(" ", 1)[1])

        elif head == "function":
            # 调用轻雪函数
            return functools.partial(get_function, line.split(" ", 1)[1])


def get_function(name: str) -> LiteyukiFunction | None:
    """
    获取一个轻雪函数
    Args:
        name: 函数名
    Returns:
    """
    return loaded_functions.get(name)


def load_from_dir(path: str):
    """
    从目录中加载轻雪函数，类似mcfunction

    Args:
        path: 目录路径
    """
    for f in os.listdir(path):
        f = os.path.join(path, f)
        if os.path.isfile(f):
            if f.endswith(ly_function_extensions):
                load_from_file(f)


def load_from_file(path: str):
    """
    从文件中加载轻雪函数
    Args:
        path:
    Returns:
    """
    pass
