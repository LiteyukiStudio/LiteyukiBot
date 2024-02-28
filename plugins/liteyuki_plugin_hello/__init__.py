from nonebot import on_command
from nonebot.rule import to_me

hello = on_command('hello', aliases={'你好'}, rule=to_me())


@hello.handle()
async def handle_first_receive(bot, event, state):
    await hello.finish('Hello, world!')
