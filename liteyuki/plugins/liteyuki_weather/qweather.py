from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, Args, MultiVar, Arparma


@on_alconna(
    aliases={"天气"},
    command=Alconna(
        "weather",
        Args["keywords", MultiVar(str)],
    ),
).handle()
async def _(result: Arparma):
    """await alconna.send("weather", city)"""