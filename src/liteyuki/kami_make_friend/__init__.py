import random
import time

from nonebot import on_command, on_message
from datetime import datetime
from ..extraApi.base import Session, Command
from ..extraApi.permission import AUTHUSER, MASTER
from ..extraApi.rule import plugin_enable, NOT_IGNORED, NOT_BLOCKED, MODE_DETECT
from .mfApi import *
from ..kami_music.musicApi import getMusic

plugin_id = "kami.make_friend"

make_friend = on_command(cmd="寻找朋友",
                         rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                         permission=AUTHUSER | MASTER,
                         priority=10, block=True)
desert_friend = on_command(cmd="断绝朋友",
                           rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                           permission=AUTHUSER | MASTER,
                           priority=10, block=True)
accept = on_command(cmd="同意请求",
                    rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                    permission=AUTHUSER | MASTER,
                    priority=10, block=True)

connect = on_command(cmd="连接朋友",
                     rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                     permission=AUTHUSER | MASTER,
                     priority=10, block=True)
disconnect = on_command(cmd="断开朋友",
                        rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                        permission=AUTHUSER | MASTER,
                        priority=10, block=True)
shield = on_command(cmd="屏蔽朋友",
                    rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                    permission=AUTHUSER | MASTER,
                    priority=10, block=True)
select_song = on_command(cmd="为朋友点歌",
                         permission=AUTHUSER | MASTER,
                         rule=plugin_enable(plugin_id) & NOT_IGNORED & NOT_BLOCKED & MODE_DETECT,
                         priority=10, block=True)

msg_trans = on_message(block=True, permission=AUTHUSER | MASTER, rule=Online & Not_Disconnect & plugin_enable("kami.make_friend"))


@make_friend.handle()
async def make_friend_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    if await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None) is None:
        friend_list = await bot.get_friend_list()
        free_friend_list = []
        for friend in friend_list:
            if await ExtraData.get_user_data(user_id=friend["user_id"], key="kami.make_friend.target", default=None) is None and await ExtraData.get_user_data(
                    user_id=friend["user_id"], key="enable", default=False) and friend["user_id"] != event.user_id:
                free_friend_list.append(friend["user_id"])

        if len(free_friend_list) == 0:
            await make_friend.send(message="[系统]暂时没有用户可供匹配")
        else:
            target_id = random.choice(free_friend_list)
            await make_friend.send(message="[系统]随机匹配成功，已发送请求，待对方同意")
            # 储存请求数据
            await ExtraData.set_user_data(user_id=target_id, key="kami.make_friend.request", value=event.user_id)
            await ExtraData.set_user_data(user_id=target_id, key="kami.make_friend.request_date", value=list(time.localtime())[0:4])
            await bot.send_private_msg(user_id=target_id, message="[系统]有人想和你成为匿名朋友，发送\"同意请求\"即可与对方成为朋友，不想忽略即可")
    else:
        await make_friend.send(message="[系统]你已经有一个朋友了，不能再交新朋友了，但是你可以选择断绝朋友")


@desert_friend.handle()
async def desert_friend_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None)
    if target_id is not None:
        pass
    else:
        state["sure"] = "不确定"
        await desert_friend.send(message="[系统]断绝失败，你还没有朋友")


@desert_friend.got(key="sure", prompt="[系统]发送确定和朋友断绝关系，你真的想好了吗？")
async def desert_friend_got(bot: Bot, event: PrivateMessageEvent, state: T_State):
    state["sure"] = str(state["sure"])
    if state["sure"] == "确定":
        target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None)
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.target", value=None)
        await ExtraData.set_user_data(user_id=target_id, key="kami.make_friend.target", value=None)
        await desert_friend.send(message="[系统]朋友关系已断绝")
        await bot.send_private_msg(user_id=target_id, message="[系统]你的朋友和你断绝了关系")
    else:
        await desert_friend.send(message="[系统]断绝关系取消")


@accept.handle()
async def accept_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    request_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.request", default=None)
    request_date = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.request_date", default=None)
    my_target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None)
    ta_target_id = await ExtraData.get_user_data(user_id=request_id, key="kami.make_friend.target", default=None)
    if request_id is not None and my_target_id is None and ta_target_id is None:
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.target", value=request_id)
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.date", value=list(time.localtime())[0:4])
        await accept.send(message="[系统]你和ta成为了朋友，发送\"连接朋友\"开始与ta聊天")

        await ExtraData.set_user_data(user_id=request_id, key="kami.make_friend.target", value=event.user_id)
        await ExtraData.set_user_data(user_id=request_id, key="kami.make_friend.date", value=list(time.localtime())[0:4])
        await bot.send_private_msg(user_id=request_id, message="[系统]你发送的朋友请求得到了同意，发送\"连接朋友\"开始与ta聊天")
    else:
        await accept.send(message="[系统]同意请求失败：你没有收到朋友请求或对方已将有朋友了")


@connect.handle()
async def connect_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    state2 = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.online", default=False)
    if not state2 and await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None) is not None:
        target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None)
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.online", value=True)
        await ExtraData.set_user_data(user_id=target_id, key="kami.make_friend.online", value=True)

        await connect.send("[系统]已连接到朋友，你发送的消息会通过%s转发到朋友。无法使用机器人，若想断开请发送\"断开朋友\"" % list(bot.config.nickname)[0])
        await bot.send_private_msg(user_id=target_id, message="[系统]你的朋友主动连接到了你，你的消息都会通过%s转发到朋友。无法使用机器人。若想断请发送\"断开朋友\"" % list(bot.config.nickname)[0])

    else:
        if state2:
            await connect.send(message="[系统]已连接到朋友，无需重复操作")
        else:
            await connect.send(message="[系统]你还没有朋友，请先发送\"寻找朋友\"找一个朋友")


@disconnect.handle()
async def disconnect_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    state2 = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.online", default=False)
    if state2:
        target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=None)
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.online", value=False)
        await ExtraData.set_user_data(user_id=target_id, key="kami.make_friend.online", value=False)

        await disconnect.send(message="[系统]已断开与朋友的连接")
        await bot.send_private_msg(user_id=target_id, message="对方断开了与你的连接")
    else:
        await connect.send(message="[系统]你还没有朋友或还没有连接到朋友")


@msg_trans.handle()
async def msg_translator(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        is_badword = state.get("is_badword", False)
        if not is_badword:
            target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target", default=0)
            my_state = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.shield", default=False)
            ta_state = await ExtraData.get_user_data(user_id=target_id, key="kami.make_friend.shield", default=False)
            if my_state:
                await msg_trans.send(message="[系统]你已屏蔽朋友的消息，无法将此消息送达，要接触请再次发送\"屏蔽朋友\"")
            elif ta_state:
                pass
            else:
                await bot.send_private_msg(user_id=target_id, message=event.message)
        else:
            await msg_trans.send("[系统]你的消息含有违禁词，未被送达")
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@shield.handle()
async def shield_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    state2 = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.shield", default=False)
    if not state2:
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.shield", value=True)
        await shield.send(message="[系统]你已屏蔽朋友的消息，但是ta不知道")
    else:
        await ExtraData.set_user_data(user_id=event.user_id, key="kami.make_friend.shield", value=False)
        await shield.send(message="[系统]你已允许接收朋友的消息，ta也不知道")


@select_song.handle()
async def select_song_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    args, kws = Command.formatToCommand(cmd=event.raw_message)
    target_id = await ExtraData.get_user_data(user_id=event.user_id, key="kami.make_friend.target")
    if target_id is not None:
        state["target_id"] = target_id
        song = await getMusic(" ".join(args[1:]), plat=kws.get("plat", "163"))
        state["song"] = song
        await select_song.send(song)
    else:
        state["words"] = None
        await select_song.send(message="[系统]你还没有朋友")


@select_song.got(key="words", prompt="[系统]这是你即将点给ta的歌，你还想对他说的话是什么呢（发送\"取消点歌\"即可取消）")
async def select_song_got(bot: Bot, event: PrivateMessageEvent, state: T_State):
    if state["words"] is not None:
        if str(state["words"]).strip() == "取消点歌":
            await select_song.send(message="[系统]点歌已取消")
        else:
            await bot.send_private_msg(user_id=state["target_id"], message=state["song"])
            await bot.send_private_msg(user_id=state["target_id"], message="[系统]你的朋友给你点了一首歌，ta想对你说：" + str(state["words"]))
            await select_song.send(message="[系统]点歌和想说的话已发送到对方")
