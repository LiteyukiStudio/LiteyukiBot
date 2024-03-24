from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import Alconna, Arparma, on_alconna

from liteyuki.utils.config import config
from liteyuki.utils.ly_typing import T_Bot

cmd_liteyuki = on_alconna(
    Alconna(
        "liteyuki"
    ),
    permission=SUPERUSER
)


@cmd_liteyuki.handle()
async def _(bot: T_Bot):
    await cmd_liteyuki.finish(f"Hello, Liteyuki!\nBot {bot.self_id}\nLiteyukiID {config.get('liteyuki_id', 'No')}")
