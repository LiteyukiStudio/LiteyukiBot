from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.rule import Rule

from .utils import Command


def args_end_with(suffix: str | tuple) -> Rule:
    """
    除去关键词参数后参数组成的字符串的结尾
    :param suffix: 后缀
    :return:
    """
    async def _(bot: Bot, event: MessageEvent):
        args, kwargs = Command.formatToCommand(event.raw_message)
        return Command.formatToString(*args).endswith(suffix)
    return Rule(_)