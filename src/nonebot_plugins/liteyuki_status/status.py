from src.utils import event as event_utils
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from .api import *

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Subcommand, UniMessage

status_alc = on_alconna(
    aliases={"状态"},
    command=Alconna(
        "status",
        Subcommand(
            "memory",
            alias={"mem", "m", "内存"},
        ),
        Subcommand(
            "process",
            alias={"proc", "p", "进程"},
        ),
        Subcommand(
            "refresh",
            alias={"refr", "r", "刷新"},
        ),
    ),
)

status_card_cache = {}  # lang -> bytes


@status_alc.handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    ulang = get_user_lang(event_utils.get_user_id(event))
    global status_card_cache
    if ulang.lang_code not in status_card_cache.keys() or (
        ulang.lang_code in status_card_cache.keys()
        and time.time() - status_card_cache[ulang.lang_code][1] > 60
    ):
        status_card_cache[ulang.lang_code] = (
            await generate_status_card(
                bot=await get_bots_data(),
                hardware=await get_hardware_data(),
                liteyuki=await get_liteyuki_data(),
                lang=ulang.lang_code,
                bot_id=bot.self_id,
            ),
            time.time(),
        )
    image = status_card_cache[ulang.lang_code][0]
    await status_alc.finish(UniMessage.image(raw=image))


@status_alc.assign("memory")
async def _():
    pass


@status_alc.assign("process")
async def _():
    pass
