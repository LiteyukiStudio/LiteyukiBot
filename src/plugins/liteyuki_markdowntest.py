import nonebot
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from src.utils.adapter import T_Message, T_Bot, v11, T_MessageEvent

md_test = on_command("mdts", aliases={"会话md"}, permission=SUPERUSER)
md_group = on_command("mdg", aliases={"群md"}, permission=SUPERUSER)

placeholder = {
    "&#91;": "[",
    "&#93;": "]",
    "&amp;": "&",
    "&#44;": ",",
    "\n" : r"\n",
    "\"" : r'\\\"'
}

@md_test.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    arg = str(arg).replace("\\", "\\\\").replace("\n", "\\n")
    print(arg)
    for k, v in placeholder.items():
        arg = arg.replace(k, v)
    sfm = await bot.call_api(
        api="send_private_forward_msg",
        user_id=bot.self_id,
        messages=[
            {
                "type": "node",
                "data": {
                    "name": "Liteyuki",
                    "uin": bot.self_id,
                    "content": [
                        {
                            "type": "markdown",
                            "data": {
                                "content": '{"content":"%s"}' % arg
                            }
                        }
                    ]
                },
            },
        ]
    )
    await md_test.finish(
        message=v11.Message(
            MessageSegment(
                type="longmsg",
                data={
                    "id": sfm["forward_id"]
                }
            )
        )
    )

@md_group.handle()
async def _(bot: T_Bot, event: T_MessageEvent, arg: v11.Message = CommandArg()):
    group_id, arg = str(arg).split(" ", 1)
    print(arg)
    for k, v in placeholder.items():
        arg = arg.replace(k, v)
    nonebot.logger.info("Markdown 测试")
    sfm = await bot.call_api(
        api="send_private_forward_msg",
        user_id=bot.self_id,
        messages=[
            {
                "type": "node",
                "data": {
                    "name": "Liteyuki",
                    "uin": bot.self_id,
                    "content": [
                        {
                            "type": "markdown",
                            "data": {
                                "content": '{"content":"%s"}' % arg
                            }
                        }
                    ]
                },
            },
        ]
    )
    await bot.send_group_msg(
        message=v11.Message(
            MessageSegment(
                type="longmsg",
                data={
                    "id": sfm["forward_id"]
                }
            )
        ),
        group_id=group_id
    )