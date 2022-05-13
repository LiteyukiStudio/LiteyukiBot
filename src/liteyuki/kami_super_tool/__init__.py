from extraApi.base import Command, ExtraData, Session
from extraApi.permission import AUTHUSER
from extraApi.rule import pluginEnable
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, PrivateMessageEvent, GroupMessageEvent, GROUP_OWNER, GROUP_ADMIN
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State

setConfig = on_command(cmd="设置属性", rule=pluginEnable("kami.super_tool"), permission=SUPERUSER, priority=10, block=True)
getConfig = on_command(cmd="获取属性", rule=pluginEnable("kami.super_tool"), permission=AUTHUSER, priority=10, block=True)


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

        if targetType in ["g", "gm"] and (await GROUP_OWNER(bot, event) or await GROUP_ADMIN(bot, event)) or await SUPERUSER(bot, event) or targetType == "u" and event.user_id == int(targetId):
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
