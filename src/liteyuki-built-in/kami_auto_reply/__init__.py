import copy
import time

import asyncio

import requests
from nonebot import on_message, on_command
from nonebot.adapters.onebot.v11 import Message, PRIVATE_FRIEND
from nonebot.params import CommandArg
from nonebot.utils import run_sync
from numpy import mean
from .arApi import *
from ...extraApi.badword import *
from ...extraApi.rule import *

listener = on_message(priority=100, block=False)
editReply = on_command(cmd="添加回复", aliases={"删除回复", "清除回复", "添加全局回复", "删除全局回复", "清除全局回复"},
                       permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | PRIVATE_FRIEND,
                       priority=1, block=True)
set_reply_probability = on_command(cmd="设置回复率",
                                   permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | PRIVATE_FRIEND,
                                   priority=1, block=True)
set_ai_reply = on_command(cmd="启用智能回复", aliases={"停用智能回复"},
                          permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | PRIVATE_FRIEND,
                          priority=1, block=True)


@set_reply_probability.handle()
async def set_reply_probability_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State, args: Message = CommandArg()):
    probability = Balance.clamp(float(str(args)), 0.0, 1.0)
    await ExtraData.setData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.reply_probability", value=probability)
    await set_reply_probability.send(message="已将此会话中回复率设置为:%s" % probability)


@set_ai_reply.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    state_0 = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.enable_ai",
                                      default=True if isinstance(event, PrivateMessageEvent) else False)
    if "启用" in event.raw_message:
        if state_0:
            await set_ai_reply.send(message="当前会话智能回复已启用，无需重复操作")
        else:
            await set_ai_reply.send(message="当前会话智能回复启用成功")
            await ExtraData.setData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.enable_ai", value=False)
    else:
        if not state_0:
            await set_ai_reply.send(message="当前会话智能回复已停用，无需重复操作")
        else:
            await set_ai_reply.send(message="当前会话智能回复停用成功")
            await ExtraData.setData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.enable_ai", value=False)


@listener.handle()
async def listenerHandle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    event.raw_message = Command.escape(event.raw_message)

    # if random.random() < session_reply_probability * favo_reply_probability or await to_me()(bot, event, state) or await ExtraData.get_user_data(event.user_id,
    #                                                                                                                                              key="my.user_call_bot",
    #                                                                                                                                              default=list(bot.config.nickname)[
    #                                                                                                                                                  0]) in event.raw_message:
    reply = await get_database_reply(bot, event, state)
    session_reply_probability = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.reply_probability",
                                                        default=1.0)
    session_enable_ai = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="kami.auto_reply.enable_ai",
                                                default=True if isinstance(event, PrivateMessageEvent) else False)

    if session_enable_ai and reply is None:
        # 基于好感度的回复
        favo_reply_probability = (Balance.clamp(await Balance.getFavoValue(event.user_id) / 200, 0, 1))
        reply = await get_ai_reply(bot, event, state)
    if reply is not None and random.random() <= session_reply_probability:
        user_call_bot = await ExtraData.get_user_data(user_id=event.user_id, key="my.user_call_bot", default=list(bot.config.nickname)[0])
        placeholder = {
            "%msg%": Command.escape(event.raw_message),
            "%time1%": "%s:%s" % tuple(list(time.localtime())[3:5]),
            "%time2%": "%s:%s:%s" % tuple(list(time.localtime())[3:6]),
            "%date%": "%s-%s-%s" % tuple(list(time.localtime())[0:3]),
            "%at%": "[CQ:at,qq=%s]" % str(event.user_id),
            "%user_id%": str(event.user_id),
            "%bot_name%": random.choice(list(bot.config.nickname)),
            "%call_bot%": user_call_bot,
            "%call%": await ExtraData.getData(targetType=ExtraData.User, targetId=event.user_id, key="my.bot_call_user",
                                              default=event.sender.nickname),
            "%nickname%": event.sender.nickname
        }
        # 遍历和替换
        replace_items = placeholder.items()
        for old, new in replace_items:
            reply = reply.replace(old, new)

        # %url,http:a.a.a,json,a.b.c.d,url%
        url_search = re.findall("%url,.+?[^\\\\],.+?[^\\\\],.+?[^\\\\],url%", reply)
        url_rph = "1145141919810hhhaaaa"
        for url_ph in url_search:
            url_ph.replace("\\,", url_rph)
            params = url_ph[5: -5].split(",")
            new_params = []
            for p in params:
                new_params.append(p.replace(url_rph, ","))
            data = await run_sync(requests.get)(url=new_params[0], headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
            })
            if new_params[1] == "json":
                json_key_seq = new_params[2].split("/")
                sub_data = copy.deepcopy(data.json())
                for seq in json_key_seq:
                    try:
                        seq = int(seq)
                    except:
                        seq = str(seq)
                    sub_data = sub_data[seq]
                target_text = str(sub_data)
            else:
                target_text = str(data.text)
            reply = reply.replace(url_ph, target_text)

        await Balance.editFavoValue(user_id=event.user_id, delta=random.randint(1, 3), reason="互动：%s" % reply)
        await Balance.editCoinValue(user_id=event.user_id, delta=random.randint(1, 2), reason="互动：%s" % reply)

        reply = await badwordFilter(bot, event, state, reply)

        reply_format_list = reply.replace("。", "||").replace("!", "||").replace("，", "||").replace("\n", "||").split("||")

        if random.random() <= 0.5 and len(reply_format_list) <= 10 and mean([len(seg) for seg in reply_format_list]) >= 5 or "||" in reply:
            for reply_seg in reply_format_list:
                await asyncio.sleep(Balance.clamp(random.randint(len(reply_seg) - 3, len(reply_seg) + 3) * 0.25, 0.5, 1.0))
                await listener.finish(message=Message(reply_seg))
        else:
            await listener.finish(message=Message(reply))


@editReply.handle()
async def editReplyHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        event.raw_message = event.raw_message.strip().replace("&#91;", "[").replace("&#93;", "]")
        args, kws = Command.formatToCommand(event.raw_message, kw=False)
        op = args[0][0:2]
        mode = args[1]
        if mode not in ["re", "tmre", "eq", "tmeq"]:
            await editReply.finish("%s自动回复模式出错:%s" % (op, mode))

        if "全局" == args[0][2:4] and await SUPERUSER(bot, event):
            replyData = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="auto_reply", default={})
            globalMode = True
        else:
            replyData = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                                key="auto_reply", default={})
            globalMode = False

        state["replyData"] = replyData
        state["op"] = op
        state["mode"] = mode
        state["globalMode"] = globalMode
        state["args"] = args
        if len(args) >= 3:
            state["match"] = args[2]
        else:
            await editReply.send("匹配内容是什么呢", at_sender=True)
    except BaseException as e:
        state["match"] = None
        state["reply"] = None
        await Session.sendException(bot, event, state, e, "也许是命令格式错误, 请使用\"help 自动回复\"进行查看")


@editReply.got("match")
async def editReplyGotMatch(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        if len(state["args"]) >= 4:
            reply = Command.formatToString(*state["args"][3:]).replace("%20", " ")
            state["reply"] = reply
        else:
            if state["op"] == "清除":
                state["reply"] = "None"
            else:
                await editReply.send(message="回复内容是什么呢", at_sender=True)
        state["match"] = str(state["match"])
    except BaseException as e:
        await Session.sendException(bot, event, state, e, "也许是命令格式错误, 请使用\"help 自动回复\"进行查看")


@editReply.got("reply")
async def editReplyGotReply(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        if state["reply"] is None:
            await editReply.finish()
        op = state["op"]
        mode = state["mode"]
        match = state["match"]
        reply = str(state["reply"])
        replyData = state["replyData"]
        globalModeText = "全局" if state["globalMode"] else "此会话中"
        if mode in ["re", "tmre"] and Command.reExpressionChecker(match) or mode in ["eq", "tmeq"]:
            pass
        else:
            await editReply.finish(message="%s%s回复失败:\n正则表达式:\"%s\"有错或过于宽泛" % (op, globalModeText, match))

        if op == "添加":
            if mode in replyData:
                if match in replyData[mode]:
                    if reply not in replyData[mode][match]:
                        replyData[mode][match].append(reply)
                        r = "添加%s回复成功:\n匹配:[%s]%s\n回复:%s" % (globalModeText, mode, match, reply)
                    else:
                        r = "添加%s回复失败:\n[%s]%s中已存在回复:%s" % (globalModeText, mode, match, reply)
                else:
                    replyData[mode][match] = [reply]
                    r = "添加%s回复成功:\n匹配:[%s]%s\n回复:%s" % (globalModeText, mode, match, reply)
            else:
                replyData[mode] = {match: [reply]}
                r = "添加%s回复成功:\n匹配:[%s]%s\n回复:%s" % (globalModeText, mode, match, reply)
        elif op == "删除":
            if mode in replyData:
                if match in replyData[mode]:
                    if reply in replyData[mode][match]:
                        replyData[mode][match].remove(reply)
                        if len(replyData[mode][match]) == 0:
                            del replyData[mode][match]
                        r = "删除%s回复成功:\n匹配:[%s]%s\n回复:%s" % (globalModeText, mode, match, reply)
                    else:
                        r = "删除%s回复失败:\n[%s]%s中不存在回复:%s" % (globalModeText, mode, match, reply)
                else:
                    r = "删除%s回复失败:\n匹配:[%s]%s不存在" % (globalModeText, mode, match)
            else:
                r = "删除%s回复失败:\n模式:[%s]不存在" % (globalModeText, mode)
        elif op == "清除":
            if mode in replyData:
                if match in replyData[mode]:
                    del replyData[mode][match]
                    r = "清除%s回复成功:\n匹配:[%s]%s" % (globalModeText, mode, match)
                else:
                    r = "清除%s回复失败:\n匹配:[%s]%s不存在" % (globalModeText, mode, match)
            else:
                r = "清除%s回复失败:\n模式:[%s]不存在" % (globalModeText, mode)
        else:
            r = "编辑自动回复<操作>参数出错"

        if state["globalMode"]:
            rd = await ExtraData.setData(targetType=ExtraData.Group, targetId=0, key="auto_reply", value=replyData)
        else:
            rd = await ExtraData.setData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                         key="auto_reply", value=replyData)
        if rd:
            await editReply.send(message=Message(r), at_sender=True)
            session = await Log.get_session_name(bot, event)
            await Log.plugin_log("kami_auto_reply", "%s:%s" % (session, r))
        else:
            await editReply.send(message="自动回复数据储存出错", at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e, "也许是命令格式错误, 请使用\"help 自动回复\"进行查看")
