import asyncio
import random

import nonebot
from nonebot import Bot, on_message, get_driver, require
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State

from src.utils.base.ly_typing import T_MessageEvent
from .utils import get_keywords
from src.utils.base.word_bank import get_reply
from src.utils.event import get_message_type
from src.utils.base.permission import GROUP_ADMIN, GROUP_OWNER
from src.utils.base.data_manager import group_db, Group

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Arparma

nicknames = set()
driver = get_driver()
group_reply_probability: dict[str, float] = {
}
default_reply_probability = 0.05
cut_probability = 0.4  # 分几句话的概率


@on_alconna(
    Alconna(
        "set-reply-probability",
        Args["probability", float, default_reply_probability],
    ),
    aliases={"设置回复概率"},
    permission=SUPERUSER | GROUP_ADMIN | GROUP_OWNER,
).handle()
async def _(result: Arparma, event: T_MessageEvent, matcher: Matcher):
    # 修改内存和数据库的概率值
    if get_message_type(event) == "group":
        group_id = event.group_id
        probability = result.main_args.get("probability")
        # 保存到数据库
        group: Group = group_db.where_one(Group(), "group_id = ?", group_id, default=Group(group_id=str(group_id)))
        group.config["reply_probability"] = probability
        group_db.save(group)

        await matcher.send(f"已将群组{group_id}的回复概率设置为{probability}")
    return


@group_db.on_save
def _(model: Group):
    """
    在数据库更新时，更新内存中的回复概率
    Args:
        model:

    Returns:

    """
    group_reply_probability[model.group_id] = model.config.get("reply_probability", default_reply_probability)


@driver.on_bot_connect
async def _(bot: Bot):
    global nicknames
    nicknames.update(bot.config.nickname)
    # 从数据库加载群组的回复概率
    groups = group_db.where_all(Group(), default=[])
    for group in groups:
        group_reply_probability[group.group_id] = group.config.get("reply_probability", default_reply_probability)


@on_message(priority=100).handle()
async def _(event: T_MessageEvent, bot: Bot, state: T_State, matcher: Matcher):
    kws = await get_keywords(event.message.extract_plain_text())

    tome = False
    if await to_me()(event=event, bot=bot, state=state):
        tome = True
    else:
        for kw in kws:
            if kw in nicknames:
                tome = True
                break

    # 回复概率
    message_type = get_message_type(event)
    if tome or message_type == "private":
        p = 1.0
    else:
        p = group_reply_probability.get(event.group_id, default_reply_probability)

    if random.random() < p:
        if reply := get_reply(kws):
            if random.random() < cut_probability:
                reply = reply.replace("。", "||").replace("，", "||").replace("！", "||").replace("？", "||")
                replies = reply.split("||")
                for r in replies:
                    if r:  # 防止空字符串
                        await asyncio.sleep(random.random() * 2)
                        await matcher.send(r)
            else:
                await asyncio.sleep(random.random() * 3)
                await matcher.send(reply)
            return
