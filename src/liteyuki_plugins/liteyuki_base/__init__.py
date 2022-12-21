from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, GroupMessageEvent, PrivateMessageEvent, Bot
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

echo = on_command(cmd="echo", permission=SUPERUSER)
liteyuki = on_command(cmd="liteyuki", permission=SUPERUSER)

@echo.handle()
async def _(bot: Bot, event: PrivateMessageEvent, args: Message = CommandArg()):
    await echo.send(args)
