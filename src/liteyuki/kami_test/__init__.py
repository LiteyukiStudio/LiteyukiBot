from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot

m = on_command(cmd="liteyuki")


@m.handle()
async def testHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    await m.send("轻雪机器人:测试成功")
