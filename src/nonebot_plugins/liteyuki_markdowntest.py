from nonebot import on_command, require
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from src.utils.base.ly_typing import T_Bot, T_MessageEvent, v11
from src.utils.message.message import MarkdownMessage as md, broadcast_to_superusers
from src.utils.message.html_tool import *

md_test = on_command("mdts", permission=SUPERUSER)
btn_test = on_command("btnts", permission=SUPERUSER)
latex_test = on_command("latex", permission=SUPERUSER)


@md_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    await md.send_md(
        v11.utils.unescape(str(arg)),
        bot,
        message_type=event.message_type,
        session_id=event.user_id if event.message_type == "private" else event.group_id
    )


@btn_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    await md.send_btn(
        str(arg),
        bot,
        message_type=event.message_type,
        session_id=event.user_id if event.message_type == "private" else event.group_id
    )


@latex_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    latex_text = f"$${v11.utils.unescape(str(arg))}$$"
    img = await md_to_pic(latex_text)
    await bot.send(event=event, message=MessageSegment.image(img))


__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪Markdown测试",
    description="用于测试Markdown的插件",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
            "liteyuki": True,
    }
)
