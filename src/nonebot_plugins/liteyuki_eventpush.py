import nonebot
from nonebot import on_message, require
from nonebot.plugin import PluginMetadata

from src.utils.base.data import Database, LiteModel
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna
from arclet.alconna import Arparma, Alconna, Args, Option, Subcommand


class Node(LiteModel):
    TABLE_NAME: str = "node"
    bot_id: str = ""
    session_type: str = ""
    session_id: str = ""

    def __str__(self):
        return f"{self.bot_id}.{self.session_type}.{self.session_id}"


class Push(LiteModel):
    TABLE_NAME: str = "push"
    source: Node = Node()
    target: Node = Node()
    inde: int = 0


pushes_db = Database("data/pushes.ldb")
pushes_db.auto_migrate(Push(), Node())

alc = Alconna(
    "lep",
    Subcommand(
        "add",
        Args["source", str],
        Args["target", str],
        Option("bidirectional", Args["bidirectional", bool])
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
            push1 = Push(
                source=Node(bot_id=source[0], session_type=source[1], session_id=source[2]),
                target=Node(bot_id=target[0], session_type=target[1], session_id=target[2]),
                inde=len(pushes_db.where_all(Push(), default=[]))
            )
            pushes_db.save(push1)

            if result.subcommands["add"].args.get("bidirectional"):
                push2 = Push(
                    source=Node(bot_id=target[0], session_type=target[1], session_id=target[2]),
                    target=Node(bot_id=source[0], session_type=source[1], session_id=source[2]),
                    inde=len(pushes_db.where_all(Push(), default=[]))
                )
                pushes_db.save(push2)
            await add_push.finish("添加成功")
        else:
            await add_push.finish("参数缺失")
    elif result.subcommands.get("rm"):
        index = result.subcommands["rm"].args.get("index")
        if index is not None:
            try:
                pushes_db.delete(Push(), "inde = ?", index)
                await add_push.finish("删除成功")
            except IndexError:
                await add_push.finish("索引错误")
        else:
            await add_push.finish("参数缺失")
    elif result.subcommands.get("list"):
        await add_push.finish(
            "\n".join([f"{push.inde} {push.source.bot_id}.{push.source.session_type}.{push.source.session_id} -> "
                       f"{push.target.bot_id}.{push.target.session_type}.{push.target.session_id}" for i, push in
                       enumerate(pushes_db.where_all(Push(), default=[]))]))
    else:
        await add_push.finish("参数错误")


@on_message(block=False).handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    for push in pushes_db.where_all(Push(), default=[]):
        if str(push.source) == f"{bot.self_id}.{event.message_type}.{event.user_id if event.message_type == 'private' else event.group_id}":
            bot2 = nonebot.get_bot(push.target.bot_id)
            msg_formatted = ""
            for line in str(event.message).split("\n"):
                msg_formatted += f"**{line.strip()}**\n"
            push_message = (
                f"> From {event.sender.nickname}@{push.source.session_type}.{push.source.session_id}\n> Bot {bot.self_id}\n\n"
                f"{msg_formatted}")
            await md.send_md(push_message, bot2, message_type=push.target.session_type,
                             session_id=push.target.session_id)
    return


__author__ = "snowykami"
__plugin_meta__ = PluginMetadata(
    name="轻雪事件推送",
    description="事件推送插件，支持单向和双向推送，支持跨Bot推送",
    usage="",
    homepage="https://github.com/snowykami/LiteyukiBot",
    extra={
        "liteyuki": True,
    }
)
