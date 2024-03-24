from nonebot import require
from nonebot.permission import SUPERUSER

from liteyuki.utils.config import config
from liteyuki.utils.ly_typing import T_Bot

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna

cmd_liteyuki = on_alconna(
    Alconna(
        "liteyuki"
    ),
    permission=SUPERUSER
)


@cmd_liteyuki.handle()
async def _(bot: T_Bot):
    await cmd_liteyuki.finish(f"Hello, Liteyuki!\nBot {bot.self_id}\nLiteyukiID {config.get('liteyuki_id', 'No')}")
