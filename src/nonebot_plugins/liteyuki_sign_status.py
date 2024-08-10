import datetime
import time

import aiohttp
from nonebot import require
from nonebot.plugin import PluginMetadata

from src.utils.base.config import get_config
from src.utils.base.data import Database, LiteModel
from src.utils.base.resource import get_path
from src.utils.message.html_tool import template2image

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_alconna import Alconna, AlconnaResult, CommandResult, Subcommand, UniMessage, on_alconna, Args

__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="签名服务器状态",
    description="适用于ntqq的签名状态查看",
    usage=(
            "sign count 查看当前签名数\n"
            "sign data 查看签名数变化\n"
            "sign chart [limit] 查看签名数变化图表\n"
    ),
    type="application",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki"      : True,
            "toggleable"    : True,
            "default_enable": True,
    }
)

SIGN_COUNT_URLS: dict[str, str] = get_config("sign_count_urls", None)
SIGN_COUNT_DURATION = get_config("sign_count_duration", 10)


class SignCount(LiteModel):
    TABLE_NAME: str = "sign_count"
    time: float = 0.0
    count: int = 0
    sid: str = ""


sign_db = Database("data/liteyuki/ntqq_sign.ldb")
sign_db.auto_migrate(SignCount())

sign_status = on_alconna(Alconna(
    "sign",
    Subcommand(
        "chart",
        Args["limit", int, 10000]
    ),
    Subcommand(
        "count"
    ),
    Subcommand(
        "data"
    )
))

cache_img: bytes = None


@sign_status.assign("count")
async def _():
    reply = "Current sign count:"
    for name, count in (await get_now_sign()).items():
        reply += f"\n{name}: {count[1]}"
    await sign_status.send(reply)


@sign_status.assign("data")
async def _():
    query_stamp = [1, 5, 10, 15]

    reply = "QPS from last " + ", ".join([str(i) for i in query_stamp]) + "mins"
    for name, url in SIGN_COUNT_URLS.items():
        count_data = []
        for stamp in query_stamp:
            count_rows = sign_db.where_all(SignCount(), "sid = ? and time > ?", url, time.time() - 60 * stamp)
            if len(count_rows) < 2:
                count_data.append(-1)
            else:
                count_data.append((count_rows[-1].count - count_rows[0].count)/(stamp*60))
        reply += f"\n{name}: " + ", ".join([f"{i:.1f}" for i in count_data])
    await sign_status.send(reply)


@sign_status.assign("chart")
async def _(arp: CommandResult = AlconnaResult()):
    limit = arp.result.subcommands.get("chart").args.get("limit")
    if limit == 10000:
        if cache_img:
            await sign_status.send(UniMessage.image(raw=cache_img))
            return
    img = await generate_chart(limit)
    await sign_status.send(UniMessage.image(raw=img))


@scheduler.scheduled_job("interval", seconds=SIGN_COUNT_DURATION, next_run_time=datetime.datetime.now())
async def update_sign_count():
    global cache_img
    if not SIGN_COUNT_URLS:
        return
    data = await get_now_sign()
    for name, count in data.items():
        await save_sign_count(count[0], count[1], SIGN_COUNT_URLS[name])

    cache_img = await generate_chart(10000)


async def get_now_sign() -> dict[str, tuple[float, int]]:
    """
    Get the sign count and the time of the latest sign
    Returns:
        tuple[float, int] | None: (time, count)
    """
    data = {}
    now = time.time()
    async with aiohttp.ClientSession() as client:
        for name, url in SIGN_COUNT_URLS.items():
            async with client.get(url) as resp:
                count = (await resp.json())["count"]
                data[name] = (now, count)
    return data


async def save_sign_count(timestamp: float, count: int, sid: str):
    """
    Save the sign count to the database
    Args:
        sid:        the sign id， use url as the id
        count:
        timestamp (float): the time of the sign count         (int): the count of the sign
    """
    sign_db.save(SignCount(time=timestamp, count=count, sid=sid))


async def generate_chart(limit):
    data = []
    for name, url in SIGN_COUNT_URLS.items():
        count_rows = sign_db.where_all(SignCount(), "sid = ? ORDER BY id DESC LIMIT ?", url, limit)
        count_rows.reverse()
        data.append(
            {
                    "name"  : name,
                    # "data": [[row.time, row.count] for row in count_rows]
                    "times" : [row.time for row in count_rows],
                    "counts": [row.count for row in count_rows]
            }
        )

    img = await template2image(
        template=get_path("templates/sign_status.html"),
        templates={
                "data": data
        },
    )

    return img
