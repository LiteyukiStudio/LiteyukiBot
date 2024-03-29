from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.permission import SUPERUSER
from liteyuki.utils.htmlrender import render_html

from liteyuki.utils.resource import get
from nonebot import on_command

stats = on_command("stats", priority=5, permission=SUPERUSER)


@stats.handle()
async def _():
    html = get("templates/stats.html")
    html_bytes = await render_html(open(html, "r", encoding="utf-8").read())
    await stats.finish(MessageSegment.image(html_bytes))
