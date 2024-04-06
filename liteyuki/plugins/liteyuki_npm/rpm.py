# 轻雪资源包管理器
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma

from liteyuki.utils.ly_typing import T_Bot

list_rp = on_alconna(
    aliases={"列出资源包", "资源包列表"},
    command=Alconna(
        "list",
        Args["page", int, 1]["num", int, 10],
    ),
    permission=SUPERUSER
)

@list_rp.handle()
async def _(bot: T_Bot):
    pass