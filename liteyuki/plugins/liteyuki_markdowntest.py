import nonebot
from nonebot import on_command
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent, v11
from liteyuki.utils.message import Markdown as md

md_test = on_command("mdts", aliases={"会话md"}, permission=SUPERUSER)

placeholder = {
        "&#91;": "[",
        "&#93;": "]",
        "&amp;": "&",
        "&#44;": ",",
        "\n"   : r"\n",
        "\""   : r'\\\"'
}


@md_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    await md.send_md(
        str(arg),
        bot,
        message_type=event.message_type,
        session_id=event.user_id if event.message_type == "private" else event.group_id
    )

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
