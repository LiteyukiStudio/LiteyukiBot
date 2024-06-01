"""
liteyuki function是一种类似于mcfunction的函数，用于在liteyuki中实现一些功能，例如自定义指令等，也可与Python函数绑定
使用 /function function_name *args **kwargs来调用
例如 /function test/hello user_id=123456
可以用于一些轻量级插件的编写，无需Python代码
SnowyKami
"""
import asyncio
import functools
# cmd *args **kwargs
# api api_name **kwargs
import os
from typing import Any, Awaitable, Callable, Coroutine

import nonebot
from nonebot import Bot
from nonebot.adapters.satori import bot
from nonebot.internal.matcher import Matcher

ly_function_extensions = (
        "lyf",
        "lyfunction",
        "mcfunction"
)

loaded_functions = dict()


class LiteyukiFunction:
    def __init__(self, name: str):
        self.name = name
        self.functions: list[str] = list()
        self.bot: Bot = None
        self.kwargs_data = dict()
        self.args_data = list()
        self.matcher: Matcher = None
        self.end = False

        self.sub_tasks: list[asyncio.Task] = list()

    async def __call__(self, *args, **kwargs):
        self.kwargs_data.update(kwargs)
        self.args_data = list(set(self.args_data + list(args)))
        for i, cmd in enumerate(self.functions):
            r = await self.execute_line(cmd, i, *args, **kwargs)
            if r == 0:
                msg = f"End function {self.name} by line {i}"
                nonebot.logger.debug(msg)
                for task in self.sub_tasks:
                    task.cancel(msg)
                return

    def __str__(self):
        return f"LiteyukiFunction({self.name})"

    def __repr__(self):
        return self.__str__()

    async def execute_line(self, cmd: str, line: int = 0, *args, **kwargs) -> Any:
        """
        解析一行轻雪函数
        Args:
            cmd: 命令
            line: 行数
        Returns:
        """

        try:
            if "${" in cmd:
                # 此种情况下，{}内容不用管，只对${}内的内容进行format
                for i in range(len(cmd) - 1):
                    if cmd[i] == "$" and cmd[i + 1] == "{":
                        end = cmd.find("}", i)
                        key = cmd[i + 2:end]
                        cmd = cmd.replace(f"${{{key}}}", str(self.kwargs_data.get(key, "")))
            else:
                cmd = cmd.format(*self.args_data, **self.kwargs_data)
        except Exception as e:
            pass

        no_head = cmd.split(" ", 1)[1] if len(cmd.split(" ")) > 1 else ""
        try:
            head, cmd_args, cmd_kwargs = self.get_args(cmd)
        except Exception as e:
            error_msg = f"Parsing error in {self.name} at line {line}: {e}"
            nonebot.logger.error(error_msg)
            await self.matcher.send(error_msg)
            return

        if head == "var":
            # 变量定义
            self.kwargs_data.update(cmd_kwargs)

        elif head == "cmd":
            # 在当前计算机上执行命令
            os.system(no_head)

        elif head == "api":
            # 调用Bot API 需要Bot实例
            await self.bot.call_api(cmd_args[1], **cmd_kwargs)

        elif head == "function":
            # 调用轻雪函数
            func = get_function(cmd_args[1])
            func.bot = self.bot
            func.matcher = self.matcher
            await func(*cmd_args[2:], **cmd_kwargs)

        elif head == "sleep":
            # 等待一段时间
            await asyncio.sleep(float(cmd_args[1]))

        elif head == "nohup":
            # 挂起运行
            task = asyncio.create_task(self.execute_line(no_head))
            self.sub_tasks.append(task)

        elif head == "end":
            # 结束所有函数
            self.end = True
            return 0


        elif head == "await":
            # 等待所有协程执行完毕
            await asyncio.gather(*self.sub_tasks)

    def get_args(self, line: str) -> tuple[str, tuple[str, ...], dict[str, Any]]:
        """
        获取参数
        Args:
            line: 命令
        Returns:
            命令头 参数 关键字
        """
        line = line.replace("\\=", "EQUAL_SIGN")
        head = ""
        args = list()
        kwargs = dict()
        for i, arg in enumerate(line.split(" ")):
            if "=" in arg:
                key, value = arg.split("=", 1)
                value = value.replace("EQUAL_SIGN", "=")
                try:
                    value = eval(value)
                except:
                    value = self.kwargs_data.get(value, value)
                kwargs[key] = value
            else:
                if i == 0:
                    head = arg
                args.append(arg)
        return head, tuple(args), kwargs


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
    从目录及其子目录中递归加载所有轻雪函数，类似mcfunction

    Args:
        path: 目录路径
    """
    for f in os.listdir(path):
        f = os.path.join(path, f)
        if os.path.isfile(f):
            if f.endswith(ly_function_extensions):
                load_from_file(f)
        if os.path.isdir(f):
            load_from_dir(f)


def load_from_file(path: str):
    """
    从文件中加载轻雪函数
    Args:
        path:
    Returns:
    """
    with open(path, "r", encoding="utf-8") as f:
        name = ".".join(os.path.basename(path).split(".")[:-1])
        func = LiteyukiFunction(name)
        for i, line in enumerate(f.read().split("\n")):
            if line.startswith("#") or line.strip() == "":
                continue
            func.functions.append(line)
        loaded_functions[name] = func
        nonebot.logger.debug(f"Loaded function {name}")
