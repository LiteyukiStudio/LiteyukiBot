import asyncio
import random

from nonebot import on_command
from nonebot.adapters.onebot.v11 import GROUP_OWNER, GROUP_ADMIN, Message
from nonebot.internal.permission import Permission
from nonebot.permission import SUPERUSER

from extraApi.rule import plugin_enable
from .stApi import *

setConfig = on_command(cmd="设置属性", rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
getConfig = on_command(cmd="获取属性", rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
send_mutil_msg = on_command(cmd="群发消息", rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
backup_data = on_command(cmd="备份数据", rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
statistics_data = on_command(cmd='统计数据', rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
call_api = on_command(cmd="api", rule=plugin_enable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)


@setConfig.handle()
async def setConfigHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(event.raw_message)
        targetType = args[1]
        targetId = args[2]
        key = args[3]
        value = eval(args[4])
        if targetType == "gm":
            r = await ExtraData.set_group_member_data(event.group_id, targetId, key=key, value=value)
            if r:
                await setConfig.send("属性设置成功:\n%s%s\n%s:%s" % tuple(args[1:]))
            else:
                await setConfig.send("属性设置失败")
        else:
            r = await ExtraData.setData(targetType=targetType, targetId=targetId, key=key, value=value)
            if r:
                await setConfig.send("属性设置成功:\n%s%s\n%s:%s" % tuple(args[1:]))
            else:
                await setConfig.send("属性设置失败")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@getConfig.handle()
async def getConfigHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(event.raw_message)
        targetType = args[1]
        targetId = int(args[2])
        key = args[3]

        if targetType in ["g", "gm"] and await(GROUP_OWNER | GROUP_ADMIN | SUPERUSER)(bot, event) or await SUPERUSER(bot, event):
            if targetType == "gm":
                r = await ExtraData.get_group_member_data(event.group_id, targetId, key=key)
            else:
                r = await ExtraData.getData(targetType=targetType, targetId=targetId, key=key)
            args = list(args)
            args.append(r)
            args.append(type(r))
            await getConfig.send("%s%s\n%s:%s[%s]" % tuple(args[1:]))
        else:
            await getConfig.send("你没有权限查看此条目", at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@send_mutil_msg.handle()
async def send_mutil_msg_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    friend_list = await bot.get_friend_list()
    args = event.raw_message.split()
    msg = Message(" ".join(args[1:]))
    for friend in friend_list:
        try:
            friend_info = await bot.get_stranger_info(user_id=friend["user_id"])
            if await ExtraData.get_user_data(user_id=friend["user_id"], key="enable", default=False):
                await bot.send_private_msg(user_id=friend["user_id"], message=msg)
                await send_mutil_msg.send(message="消息已发送到：%s(%s)" % (friend_info["nickname"], friend["user_id"]))
        except BaseException as e:
            await Session.sendException(bot, event, state, e)

        await asyncio.sleep(random.randint(15, 30))


@backup_data.handle()
async def backup_data_handle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    f, n = await backup()
    await backup_data.send(message="数据备份完成：%s，共计%s个数据库" % (f, n))


@call_api.handle()
async def call_api_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    try:
        args, kws = Command.formatToCommand(cmd=event.raw_message)
        r = await bot.call_api(args[1], **kws)
        await call_api.send(message=str(r))
    except BaseException as e:
        await Session.sendException(bot, event, state, e)
