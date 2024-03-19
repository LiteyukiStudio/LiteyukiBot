import nonebot
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from src.utils.message import send_markdown
from src.utils.typing import T_Message, T_Bot, v11, T_MessageEvent

md_test = on_command("mdts", aliases={"会话md"}, permission=SUPERUSER)
md_group = on_command("mdg", aliases={"群md"}, permission=SUPERUSER)

placeholder = {
    "&#91;": "[",
    "&#93;": "]",
    "&amp;": "&",
    "&#44;": ",",
    "\n": r"\n",
    "\"": r'\\\"'
}


@md_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    await send_markdown(
        str(arg),
        bot,
        message_type=event.message_type,
        session_id=event.user_id if event.message_type == "private" else event.group_id
    )