from nonebot import require

from liteyuki.utils.base.ly_typing import T_MessageEvent

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, MultiVar, Arparma


@on_alconna(
    aliases={"天气"},
    command=Alconna(
        "weather",
        Args["keywords", MultiVar(str)],
    ),
).handle()
async def _(result: Arparma, event: T_MessageEvent):
    """await alconna.send("weather", city)"""
    print(result["keywords"])
    if len(result["keywords"]) == 0:
        pass
