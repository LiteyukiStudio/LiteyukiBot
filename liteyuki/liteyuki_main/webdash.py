import requests
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.permission import SUPERUSER
from liteyuki.utils.htmlrender import template_to_pic, html_to_pic

from liteyuki.utils.resource import get_path
from nonebot import on_command

stats = on_command("stats", priority=5, permission=SUPERUSER)


@stats.handle()
async def _():
    image_bytes = await template_to_pic(
        template_path=get_path("templates/index.html", abs_path=True),
        templates={}

    )
    await stats.finish(MessageSegment.image(image_bytes))
