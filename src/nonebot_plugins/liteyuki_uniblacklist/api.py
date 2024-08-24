import datetime

import aiohttp
import nonebot
from nonebot import require
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot_plugin_alconna.typings import Event

require("nonebot_plugin_apscheduler")

from nonebot_plugin_apscheduler import scheduler

blacklist_data: dict[str, set[str]] = {}
blacklist: set[str] = set()


@scheduler.scheduled_job("interval", minutes=10, next_run_time=datetime.datetime.now())
async def update_blacklist():
    await request_for_blacklist()


async def request_for_blacklist():
    global blacklist
    urls = [
            "https://cdn.liteyuki.icu/static/ubl/"
    ]

    platforms = [
            "qq"
    ]

    for plat in platforms:
        for url in urls:
            url += f"{plat}.txt"
            async with aiohttp.ClientSession() as client:
                resp = await client.get(url)
                blacklist_data[plat] = set((await resp.text()).splitlines())
    blacklist = get_uni_set()
    nonebot.logger.info("blacklists updated")


def get_uni_set() -> set:
    s = set()
    for new_set in blacklist_data.values():
        s.update(new_set)
    return s


@event_preprocessor
async def pre_handle(event: Event):
    try:
        user_id = str(event.get_user_id())
    except:
        return

    if user_id in get_uni_set():
        raise IgnoredException("UserId in blacklist")
