from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message
from nonebot.message import event_preprocessor

from extraApi.badword import *
from extraApi.base import Session, Command, Balance
from extraApi.permission import MASTER
from extraApi.rule import plugin_enable, BOT_GT_USER, NOT_IGNORED, NOT_BLOCKED, MODE_DETECT
from nonebot.rule import Rule
from nonebot.exception import IgnoredException


@event_preprocessor
async def badwordWarn(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    if await IS_BADWORD(bot, event, state):
        state["is_badword"] = True
        """
        0.无操作
        1.仅撤回
        2.撤回且禁言（默认3次）
        3.撤回且禁言移除（默认9次）
        """
        if type(event) is GroupMessageEvent and await Rule(BOT_GT_USER, plugin_enable("kami.badword"), NOT_IGNORED)(bot, event, state):
            user_warn_time = await ExtraData.get_group_member_data(group_id=event.group_id, user_id=event.user_id,
                                                                   key="warn_time", default=0)
            user_warn_time += 1
            await ExtraData.set_group_member_data(group_id=event.group_id, user_id=event.user_id,
                                                  key="warn_time", value=user_warn_time)
            handle_mode = await ExtraData.get_group_data(group_id=event.group_id, key="badword_handle_mode", default=0)
            enable_delete = False
            enable_ban = False
            enable_kick = False
            max_ban_time = await ExtraData.get_group_data(group_id=event.group_id, key="badword_ban_time", default=3)
            max_kick_time = await ExtraData.get_group_data(group_id=event.group_id, key="badword_kick_time", default=9)
            if handle_mode == 1:
                enable_delete = True
            elif handle_mode == 2:
                enable_delete = True
                enable_ban = True
            elif handle_mode == 3:
                enable_delete = True
                enable_ban = True
                enable_kick = True

            if enable_delete:
                await bot.delete_msg(message_id=event.message_id)
                remain = user_warn_time % max_ban_time
                if user_warn_time % max_ban_time != 0:
                    await bot.send(event, "你的消息中含有违禁词，%s/%s后禁言" % (remain, max_ban_time), at_sender=True)
            if enable_ban and user_warn_time % max_ban_time == 0:
                await bot.set_group_ban(group_id=event.group_id, user_id=event.user_id,
                                        duration=user_warn_time // max_ban_time * 20 * 60)
                await bot.send(event, "违规次数达到上限，本次禁言%s分钟" % (user_warn_time // max_ban_time * 20), at_sender=True)
            if enable_kick and user_warn_time >= max_kick_time:
                await ExtraData.set_group_member_data(group_id=event.group_id, user_id=event.user_id, key="warn_time",
                                                      value=0)
                await bot.set_group_kick(group_id=event.group_id, user_id=event.user_id)
                await bot.send(event, "违规次数达到上限，移出群聊", at_sender=True)
        if type(event) is PrivateMessageEvent:
            await bot.send_private_msg(user_id=event.user_id, message="你的消息含有违禁词")

        await Balance.editFavoValue(user_id=event.user_id, delta=-5, reason="触发违禁词")
        event.raw_message = "***"
        event.message = Message("***")
        raise IgnoredException


editBadword = on_command(cmd="添加违禁词", aliases={"删除违禁词", "添加全局违禁词", "删除全局违禁词"},
                         permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | MASTER,
                         rule=plugin_enable("kami.badword") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                         priority=10, block=True)
listBadword = on_command(cmd="列出违禁词",
                         rule=plugin_enable("kami.badword") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                         permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | MASTER,
                         priority=10, block=True)
set_time = on_command(cmd="设置禁言次数", aliases={"设置移出次数", "设置违禁词模式"},
                      rule=plugin_enable("kami.badword") & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                      permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | MASTER,
                      priority=10, block=True)


@editBadword.handle()
async def editBadwordHandle(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    :param bot:
    :param event:
    :param state:
    :return:

    违禁词编辑
    """
    try:
        args, kws = Command.formatToCommand(event.raw_message, kw=False)
        if args[0][2:4] == "全局" and await SUPERUSER(bot, event):
            state["globalMode"] = True
        elif type(event) is GroupMessageEvent:
            state["globalMode"] = False
        else:
            await editBadword.finish(message="此会话无法编辑违禁词", at_sender=True)

        if args[0][0:2] not in ["添加", "删除"]:
            state["word"] = None
            await editBadword.finish(message="操作参数出错：%s" % args[0][0:2], at_sender=True)
        else:
            state["op"] = args[0][0:2]

        if args[1] not in ["re", "eq"]:
            state["word"] = None
            await editBadword.finish(message="模式参数出错：%s" % args[0][0:2], at_sender=True)
        else:
            state["mode"] = args[1]

        state["word"] = Command.formatToString(*args[2:]).replace("%20", " ")

        if state["mode"] == "re" and Command.reExpressionChecker(state["word"]) or state["mode"] == "eq":
            pass
        else:
            await editBadword.finish(message="%s失败：\n正则表达式:\"%s\"有错或过于宽泛" % (state["op"], state["word"]))

        if state["globalMode"]:
            data = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="badword", default={})
        else:
            data = await ExtraData.getData(targetType=ExtraData.Group, targetId=event.group_id, key="badword",
                                           default={})
        modeData = data.get(state["mode"], [])
        if state["op"] == "添加" and state["word"] not in modeData:
            modeData.append(state["word"])
        elif state["op"] == "删除" and state["word"] in modeData:
            modeData.remove(state["word"])
        else:
            await editBadword.finish("%s失败，%s违禁词中%s有此违禁词" % (
                state["op"], "全局" if state["globalMode"] else "本群", "已" if state["op"] == "添加" else "没"),
                                     at_sender=True)
        data[state["mode"]] = modeData
        await ExtraData.setData(targetType=ExtraData.Group, targetId=0 if state["globalMode"] else event.group_id,
                                key="badword", value=data)
        await editBadword.finish(message="%s%s违禁词成功" % (state["op"], "全局" if state["globalMode"] else "本群"))

    except BaseException as e:
        await Session.sendException(bot, event, state, e, text="请检查命令格式是否正确")


@listBadword.handle()
async def listBadwordHandle(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    :param bot:
    :param event:
    :param state:
    :return:

    违禁词列出
    """
    try:
        data = await ExtraData.getData(targetType=ExtraData.Group, targetId=event.group_id, key="badword", default={})
        reply = "本群违禁词如下"
        count = 0
        for match in data.items():
            mode = match[0]
            words = match[1]
            for word in words:
                count += 1
                reply += "\n[%s]%s" % (mode, word)
        if count > 0:
            await listBadword.send(message=reply)
        else:
            await listBadword.send(message="本群没有违禁词")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@set_time.handle()
async def set_time_handle(bot: Bot, event: GroupMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(cmd=event.raw_message)
        times = int(args[1])
        if args[0] in ["设置禁言次数"]:
            key = "badword_ban_time"
            reply = "已将禁言警告次数设置为：%s" % times
        elif args[0] in ["设置移出次数"]:
            key = "badword_kick_time"
            reply = "已将移出警告次数设置为：%s" % times
        else:
            key = "badword_handle_mode"
            reply = "已将违禁词模式设置为：%s" % ("无操作" if times == 0 else "仅撤回" if times == 1 else "撤回并禁言" if times == 2 else "撤回并禁言并移除" if times == 3 else "未知")
            times = Balance.clamp(times, 0, 3)
        await ExtraData.set_group_data(group_id=event.group_id, key=key, value=times)
        await bot.send(event, reply)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)
