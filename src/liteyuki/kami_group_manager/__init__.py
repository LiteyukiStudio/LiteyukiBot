import random

from extraApi.base import Command, Session, Balance, ExtraData
from extraApi.rule import *
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GROUP_OWNER, GROUP_ADMIN, Bot, GroupMessageEvent, MessageSegment, Message
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from .groupApi import *

ban = on_command(cmd="ban", aliases={"禁言", "解禁"},
                 rule=plugin_enable("kami.group_manager") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT & BOT_IS_ADMIN,
                 permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN,
                 block=True)
kick = on_command(cmd="kick", aliases={"移出", "移除"},
                  rule=plugin_enable("kami.group_manager") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT & BOT_IS_ADMIN,
                  permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN,
                  block=True)
title = on_command(cmd="头衔",
                   rule=plugin_enable("kami.group_manager") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT & BOT_IS_OWNER,
                   block=True)


@ban.handle()
async def ban_handle(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        if len(event.message) >= 3:
            target_id = event.message[1].data.get("qq", 0)
            target_info = await bot.get_group_member_info(group_id=event.group_id, user_id=target_id)
            reply = "%s成功:\n- 用户：%s（%s）" % (
                str(event.message[0]), target_info["card"] if target_info["card"] != "" else target_info["nickname"],
                target_id)
            if str(event.message[0]) != "解禁":
                duration = get_duration(str(event.message[2]).strip())
                duration = Balance.clamp(duration if duration is not None else 0, 0, 2591999)
                reply += "\n- 时长：%s" % get_duration_text(duration)
            else:
                duration = 0
            await bot.set_group_ban(group_id=event.group_id, user_id=target_id, duration=duration)
            await ban.send(message=reply)
        else:
            raise Exception("命令格式错误")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@kick.handle()
async def kick_handle(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        if len(event.message) >= 2:
            state["target_id"] = event.message[1].data.get("qq", 0)
            state["target_info"] = await bot.get_group_member_info(group_id=event.group_id, user_id=state["target_id"])
            if len(event.message) >= 3 and str(event.message[2]).strip() == "确定":
                state["determine"] = event.message[2]
            else:
                await kick.send(message="发送\"确定\"移除成员", at_sender=True)
        else:
            raise Exception("命令格式错误")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@kick.got(key="determine")
async def kick_got_determine(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        if str(state["determine"]).strip() == "确定":
            target_info = state["target_info"]
            reply = "移出成员：%s(%s)" % (
                target_info["card"] if target_info["card"] != "" else target_info["nickname"],
                state["target_id"])
            await bot.set_group_kick(group_id=event.group_id, user_id=state["target_id"])
            await kick.send(message=reply)
        else:
            await kick.send(message="移除操作已取消")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@title.handle()
async def title_handle(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        title_text = Command.formatToString(*event.raw_message.split()[1:]).replace("%20", " ")
        await bot.set_group_special_title(group_id=event.group_id, user_id=event.user_id, special_title=title_text)
        if len(title_text.encode("utf-8")) >= 19:
            await title.send(message="头衔字符超过18字节，可能会设置失败", at_sender=True)
        else:
            await title.send(message="头衔设置成功，%s" % random.choice(["快去佩戴吧！", "记得更换哦！"]), at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e, "可能是没有输入头衔文本")
