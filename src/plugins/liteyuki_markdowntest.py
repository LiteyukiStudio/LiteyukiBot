import nonebot
from nonebot import on_command, on_message
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from src.utils.message import send_markdown
from src.utils.typing import T_Message, T_Bot, v11, T_MessageEvent

md_test = on_command("mdts", aliases={"会话md"}, permission=SUPERUSER)
md_group = on_command("mdg", aliases={"群md"}, permission=SUPERUSER)
md_conv = on_command("md", block=False, permission=SUPERUSER)

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
    await send_markdown(
        str(arg),
        bot,
        message_type=event.message_type,
        session_id=event.user_id if event.message_type == "private" else event.group_id
    )


ignore_msg_ids = []
last_sent = None


@md_conv.handle()
async def _(bot: v11.Bot, event: v11.MessageEvent, arg: v11.Message = CommandArg()):
    if str(event.user_id) == str(bot.self_id) and str(bot.self_id) in ["2751454815"]:
        nonebot.logger.info("开始处理：%s" % str(event.message_id))

        data = await send_markdown(str(arg), bot, event=event)
        await bot.delete_msg(message_id=event.message_id)


__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪Markdown测试",
    description="用于测试Markdown的插件",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
)