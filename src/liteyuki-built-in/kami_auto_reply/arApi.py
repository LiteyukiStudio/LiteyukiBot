import json
import random
import re

import aiohttp

from ...extraApi.base import ExtraData
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import Rule
from nonebot.rule import to_me
from nonebot.typing import T_State


@Rule
async def MATCHPATTERN(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    reply = await getReply(bot, event, state)
    if reply is not None:
        return True
    else:
        return False


async def getReply(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    user_reply_msg_list = []
    group_reply_msg_list = []
    global_reply_msg_list = []
    resource_reply_msg_list = []
    resource_reply_dada: dict = await ExtraData.get_resource_data(key="auto_reply", default={})
    global_reply_data: dict = await ExtraData.get_global_data(key="auto_reply", default={})
    user_reply_data: dict = await ExtraData.get_user_data(user_id=event.user_id, key="auto_reply", default={})
    group_reply_data: dict = dict() if not isinstance(event, GroupMessageEvent) else await ExtraData.get_group_data(group_id=event.group_id, key="auto_reply", default={})
    # to_me : bot的第一昵称在消息中或者被at，或者用户自定义唤醒词在消息中
    if await to_me()(bot, event, state) or await ExtraData.get_user_data(event.user_id, key="my.user_call_bot", default=list(bot.config.nickname)[0]) in event.raw_message:
        tome = True
    else:
        tome = False

    # 骗ide
    items: list = user_reply_data.items()
    for match in items:
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                user_reply_msg_list.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                user_reply_msg_list.extend(replys)

    items: list = global_reply_data.items()
    for match in items:
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                global_reply_msg_list.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                global_reply_msg_list.extend(replys)

    items: list = resource_reply_dada.items()
    for match in items:
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                resource_reply_msg_list.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                resource_reply_msg_list.extend(replys)

    items: list = group_reply_data.items()
    for match in items:
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                group_reply_msg_list.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                group_reply_msg_list.extend(replys)

    items: list = resource_reply_dada.items()
    for match in items:
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                resource_reply_msg_list.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                resource_reply_msg_list.extend(replys)

    user_reply_msg_list.extend(group_reply_msg_list)
    user_reply_msg_list.extend(global_reply_msg_list)
    user_reply_msg_list.extend(resource_reply_msg_list)
    if len(user_reply_msg_list) > 0 and random.random() <= 0.75:
        return random.choice(user_reply_msg_list)
    else:
        if tome or random.random() <= 0.1:
            async with aiohttp.request("GET", url="http://api.qingyunke.com/api.php?key=free&appid=0&msg=%s" % str(event.raw_message).replace(list(bot.config.nickname)[0],
                                                                                                                                              "你")) as asyncStream:
                if (json.loads(await asyncStream.text()))["result"] == 0:
                    text = (json.loads(await asyncStream.text())).get("content").replace("菲菲", "%call_bot%")
                    text = text.replace("{br}", "\n")
                    return text
                else:
                    return random.choice(await ExtraData.get_global_data(key="register_default_reply", default=["喵喵喵"]))
        else:
            return random.choice(await ExtraData.get_global_data(key="register_default_reply", default=["喵喵喵"]))
