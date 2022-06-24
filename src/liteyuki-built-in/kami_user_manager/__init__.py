import random

from nonebot import on_message
from nonebot.adapters.onebot.v11 import Message, GROUP_OWNER, GROUP_ADMIN
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.typing import T_State

from ...extraApi.base import Session
from ...extraApi.permission import NOTAUTHUSER
from ...extraApi.rule import NOT_BLOCKED, MODE_DETECT, NOT_IGNORED
from .userApi import *
from .user_config import *

register = on_command(cmd="注册", permission=NOTAUTHUSER, priority=1, block=True)
unregister = on_message(permission=NOTAUTHUSER, priority=100, rule=to_me() & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT)

block_session_user = on_command(cmd="添加屏蔽", permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN)
ignore_session_user = on_command(cmd="添加忽略", permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN)
block_global_user = on_command(cmd="添加全局屏蔽", permission=SUPERUSER)
ignore_global_user = on_command(cmd="添加全局忽略", permission=SUPERUSER)


@register.handle()
async def registerHandle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        state["register_mode"] = await ExtraData.get_global_data(key="kami.base.verify", default=False)
        if state["register_mode"]:
            await register.send(message="请输入邮箱")
        else:
            state["authCode"] = None
            state["authCodeInput"] = None
            state["email"] = None
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@register.got(key="email")
async def registerGotEmail(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        if state["register_mode"]:
            authCode = hex(random.randint(1118481, 16777215))[2:].upper()
            await sendAuthCode(email=str(state["email"]), auth_code=authCode)
            state["authCode"] = authCode
            await register.send(message="请查收验证码邮件并在五分钟内输入")
        else:
            state["authCode"] = None
            state["authCodeInput"] = None
    except BaseException as e:
        state["authCode"] = None
        state["authCodeInput"] = None
        await Session.sendException(bot, event, state, e)


@register.got(key="authCodeInput")
async def registerGotAuthCode(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        if state["register_mode"]:
            if state["authCodeInput"] is not None:
                if state["authCode"].lower() == str(state["authCodeInput"]).lower().strip():
                    await register.send(message="验证成功, 欢迎使用轻雪机器人")
                    await ExtraData.setData(targetType=ExtraData.User, targetId=event.user_id, key="enable", value=True)
                    await ExtraData.setData(targetType=ExtraData.User, targetId=event.user_id, key="email", value=str(state["email"]))
                else:
                    await register.send(message="验证失败, 验证码错误")
        else:
            await ExtraData.setData(targetType=ExtraData.User, targetId=event.user_id, key="enable", value=True)
            await register.send(message="注册成功，欢迎使用机器人")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


# 未注册的人回复
@unregister.handle()
async def unregisterHandle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    day_times = await ExtraData.get_user_data(user_id=event.user_id, key="kami.user_manager.unregister_reply_time", default=0)
    if day_times <= 5 or isinstance(event, PrivateMessageEvent):
        await unregister.send("你还未注册，无法与%s交流，请先私聊发送\"注册\"" % list(bot.config.nickname)[0], at_sender=True)

    day_times += 1
    await ExtraData.set_user_data(user_id=event.user_id, key="kami.user_manager.unregister_reply_time", value=day_times)


def get_user_list(message: Message) -> list:
    targets_list = []
    for ms in message:
        if ms.type == "at":
            targets_list.append(int(ms.data.get("qq")))
        elif ms.type == "text":
            for uid in str(ms).strip().split():
                try:
                    targets_list.append(int(uid))
                except BaseException:
                    pass
    return targets_list


@block_session_user.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent], state: T_State, args: Message = CommandArg()):
    targets_list = get_user_list(event.message)
    old_list = await ExtraData.get_group_data(event.group_id, key="blocked_users", default=[])
    await ExtraData.set_group_data(event.group_id, key="blocked_users", value=list(set(old_list + targets_list)))
    reply = "添加本群屏蔽成功：\n"
    for uid in targets_list:
        try:
            user_info = await bot.get_group_member_info(group_id=event.group_id, user_id=uid)
        except BaseException:
            user_info = {}
        reply += '- %s(%s)\n' % (await ExtraData.getTargetCard(bot, event, uid), uid)
    await block_session_user.send(message=reply)


@ignore_session_user.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent], state: T_State, args: Message = CommandArg()):
    targets_list = get_user_list(event.message)
    old_list = await ExtraData.get_group_data(event.group_id, key="ignored_users", default=[])
    await ExtraData.set_group_data(event.group_id, key="ignored_users", value=list(set(old_list + targets_list)))
    reply = "添加本群忽略成功：\n"
    for uid in targets_list:
        try:
            user_info = await bot.get_group_member_info(group_id=event.group_id, user_id=uid)
        except BaseException:
            user_info = {}
        reply += '- %s(%s)\n' % (await ExtraData.getTargetCard(bot, event, uid), uid)
    await block_session_user.send(message=reply)


@block_global_user.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State, args: Message = CommandArg()):
    targets_list = get_user_list(event.message)
    old_list = await ExtraData.get_global_data(key="blocked_users", default=[])
    await ExtraData.set_global_data(key="blocked_users", value=list(set(old_list + targets_list)))
    reply = "添加全局屏蔽成功：\n"
    for uid in targets_list:
        try:
            user_info = await bot.get_group_member_info(group_id=event.group_id, user_id=uid)
        except BaseException:
            user_info = {}
        reply += '- %s(%s)\n' % (await ExtraData.getTargetCard(bot, event, uid), uid)
    await block_session_user.send(message=reply)


@ignore_global_user.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State, args: Message = CommandArg()):
    targets_list = get_user_list(event.message)
    old_list = await ExtraData.get_global_data(key="ignored_users", default=[])
    await ExtraData.set_global_data(key="ignored_users", value=list(set(old_list + targets_list)))
    reply = "添加全局忽略成功：\n"
    for uid in targets_list:
        try:
            user_info = await bot.get_group_member_info(group_id=event.group_id, user_id=uid)
        except BaseException:
            user_info = {}
        reply += '- %s(%s)\n' % (await ExtraData.getTargetCard(bot, event, uid), uid)
    await block_session_user.send(message=reply)
