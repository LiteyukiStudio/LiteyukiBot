import nonebot
from nonebot import require

from liteyuki.utils.config import get_config
from liteyuki.utils.ly_typing import T_Bot

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Arparma, MultiVar


@on_alconna(
    aliases={"天气"},
    command=Alconna(
        "weather",
        Args["keywords", MultiVar(str), []],
    ),
).handle()
async def _(bot: T_Bot, result: Arparma):
    """
    天气查询
    Args:
        bot:

    Returns:

    """
    print("AAA", result, result.main_args)
