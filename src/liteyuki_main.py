from nonebot import on_command
from nonebot.adapters.onebot.v11.event import MessageEvent
from nonebot.permission import SUPERUSER
import os
folders = ['plugins']
for folder in folders:
    if not os.path.exists(folder):
        os.makedirs(folder)

echo = on_command('echo', permission=SUPERUSER, priority=5)


@echo.handle()
async def _(event: MessageEvent):
    print(event.get_message())
    await echo.finish(event.get_message())
