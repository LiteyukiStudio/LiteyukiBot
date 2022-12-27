from nonebot import on_command
from nonebot.adapters.onebot.v11 import PrivateMessageEvent
from nonebot.permission import SUPERUSER
from .reloader import Reloader

reboot_matcher = on_command(
    cmd="重启",
    aliases={"reboot", "restart"},
    permission=SUPERUSER,
    priority=1,
    block=True
)

@reboot_matcher.handle()
async def _(event: PrivateMessageEvent):
    Reloader.reload()
