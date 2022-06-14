import random

from nonebot import on_message
from nonebot.rule import to_me
from nonebot.typing import T_State

from ...extraApi.base import Session
from ...extraApi.permission import NOTAUTHUSER
from ...extraApi.rule import NOT_BLOCKED, MODE_DETECT, NOT_IGNORED
from .userApi import *
from .user_config import *

register = on_command(cmd="注册", permission=NOTAUTHUSER, priority=1, block=True)
unregister = on_message(permission=NOTAUTHUSER, priority=100, rule=to_me() & NOT_BLOCKED & NOT_IGNORED & MODE_DETECT)


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
