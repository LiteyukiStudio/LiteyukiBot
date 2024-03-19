from typing import Optional

import nonebot
from nonebot import on_message
from arclet.alconna import Arparma, Alconna, Args, Option, Subcommand, Arg
from nonebot_plugin_alconna import on_alconna
from src.utils.data import LiteModel
from src.utils.message import send_markdown
from src.utils.typing import T_Bot, T_MessageEvent

pushes = []


class Node(LiteModel):
    bot_id: str
    session_type: str
    session_id: str

    def __str__(self):
        return f"{self.bot_id}.{self.session_type}.{self.session_id}"


class Push(LiteModel):
    source: Node
    target: Node


alc = Alconna(
    "lep",
    Subcommand(
        "add",
        Args["source", str],
        Args["target", str],
        Option("-b", Args["bidirectional", bool])
    ),
    Subcommand(
        "rm",
        Args["index", int],

    ),
    Subcommand(
        "list",
    )
)

add_push = on_alconna(alc)


@add_push.handle()
async def _(result: Arparma):
    """bot_id.session_type.session_id"""
    if result.subcommands.get("add"):
        source = result.subcommands["add"].args.get("source")
        target = result.subcommands["add"].args.get("target")
        if source and target:
            source = source.split(".")
            target = target.split(".")
            pushes.append(Push(
                source=Node(bot_id=source[0], session_type=source[1], session_id=source[2]),
                target=Node(bot_id=target[0], session_type=target[1], session_id=target[2])
            ))

            if result.subcommands["add"].args.get("-b"):
                pushes.append(Push(
                    source=Node(bot_id=target[0], session_type=target[1], session_id=target[2]),
                    target=Node(bot_id=source[0], session_type=source[1], session_id=source[2])
                ))

            await add_push.finish("添加成功")
        else:
            await add_push.finish("参数缺失")
    elif result.subcommands.get("rm"):
        index = result.subcommands["rm"].args.get("index")
        if index is not None:
            try:
                pushes.pop(index)
                await add_push.finish("删除成功")
            except IndexError:
                await add_push.finish("索引错误")
        else:
            await add_push.finish("参数缺失")
    elif result.subcommands.get("list"):
        await add_push.finish("\n".join([f"{i} {push.source.bot_id}.{push.source.session_type}.{push.source.session_id} -> "
                                       f"{push.target.bot_id}.{push.target.session_type}.{push.target.session_id}" for i, push in enumerate(pushes)]))
    else:
        await add_push.finish("参数错误")


@on_message(block=False).handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    for push in pushes:
        if str(push.source) == f"{bot.self_id}.{event.message_type}.{event.user_id if event.message_type == 'private' else event.group_id}":
            bot2 = nonebot.get_bot(push.target.bot_id)
            msg_formatted = ""
            for l in str(event.message).split("\n"):
                msg_formatted += f"**{l.strip()}**\n"
            push_message = f"{msg_formatted}\n\n> From {event.sender.nickname}@{push.source.session_type}.{push.source.session_id}\n> Bot {bot.self_id}"
            await send_markdown(push_message, bot2, push.target.session_type, push.target.session_id)
    return
