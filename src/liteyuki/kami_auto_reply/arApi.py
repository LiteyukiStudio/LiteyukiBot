import random
import re
from extraApi.base import ExtraData
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
    userReplyMsgList = []
    groupReplyMsgList = []
    globalReplyMsgList = []
    globalReplyData: dict = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="auto_reply", default={})
    if list(bot.config.nickname)[0] in event.raw_message or await to_me()(bot, event, state):
        tome = True
    else:
        tome = False
    userReplyData: dict = await ExtraData.getData(targetType=ExtraData.User, targetId=event.user_id, key="auto_reply", default={})
    if type(event) is GroupMessageEvent:
        groupReplyData: dict = await ExtraData.getData(targetType=ExtraData.Group, targetId=event.group_id, key="auto_reply", default={})
    else:
        groupReplyData = {}

    for match in userReplyData.items():
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                userReplyMsgList.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                userReplyMsgList.extend(replys)

    for match in globalReplyData.items():
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                globalReplyMsgList.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                globalReplyMsgList.extend(replys)

    for match in groupReplyData.items():
        mode = match[0]
        rules = match[1]
        for rule in rules.items():
            subMatch = rule[0]
            replys = rule[1]
            if (mode == "re" or mode == "tmre" and tome) and re.search(subMatch, event.raw_message) is not None:
                groupReplyMsgList.extend(replys)
            elif (mode == "eq" or mode == "tmeq" and tome) and subMatch == event.raw_message:
                groupReplyMsgList.extend(replys)

    userReplyMsgList.extend(groupReplyMsgList)
    userReplyMsgList.extend(globalReplyMsgList)
    if len(userReplyMsgList) > 0:
        return random.choice(userReplyMsgList)
    else:
        return None
