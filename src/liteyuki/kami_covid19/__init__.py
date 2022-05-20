from nonebot import on_keyword

from extraApi.rule import *
from .api import search_data

keywords = {"疫情", "新冠", "病毒"}

cmd_covid19 = on_keyword(keywords=keywords,
                         rule=plugin_enable(pluginId="kami.covid19") & NOT_IGNORED & NOT_IGNORED & MODE_DETECT,
                         priority=10)


@cmd_covid19.handle()
async def cmd_covid19_handle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    for kw in keywords:
        event.raw_message = event.raw_message.replace(kw, "")
    cityname = event.raw_message.strip()
    if cityname != "":
        state["cityname"] = cityname
    else:

        await cmd_covid19.send(message="你想查询哪里的疫情呢?", at_sender=True)


@cmd_covid19.got(key="cityname")
async def cmd_covid19_got(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    cityname = str(state["cityname"])
    message, card = await search_data(cityname)
    await cmd_covid19.send(message)
    await card.delete()
