import asyncio

from nonebot import get_bots, get_bot
from nonebot.adapters.onebot.v11 import Message
from nonebot.adapters.onebot.v11.bot import Bot

from .data import Data


async def broad_to_all_superusers(message: Message | str, white_list=None, black_list=None, interval=0):
    """
    将消息广播到所有超级用户
    白名单和黑名单只能选一个传入
    发生错误时跳到下一个

    :param interval: 相邻用户时间间隔
    :param message: 消息
    :param white_list: 白名单id
    :param black_list: 黑名单id
    :return:
    """
    for bot_id in get_bots():
        bot: Bot = get_bot(bot_id)
        for superuser_id in bot.config.superusers:
            if white_list is not None and int(superuser_id) not in white_list:
                return 0
            if black_list is not None and int(superuser_id) in black_list:
                return 0
            try:
                await bot.send_private_msg(user_id=int(superuser_id), message=message)
            except:
                pass
            await asyncio.sleep(interval)


async def broad_to_all_groups(message: Message | str, white_list=None, black_list=None, enable=True, interval=0):
    """
        将消息广播到所有群聊
        白名单和黑名单只能选一个传入
        发生错误时跳到下一个

        :param interval: 相邻会话时间间隔
        :param enable: 仅在已启用的群聊发送
        :param message:
        :param white_list: 白名单id
        :param black_list: 黑名单id
        :return:
        """
    for bot_id in get_bots():
        bot: Bot = get_bot(bot_id)
        for group in await bot.get_group_list():
            if white_list is not None and group["group_id"] not in white_list:
                return 0
            if black_list is not None and group["group_id"] in black_list:
                return 0
            if not await Data(Data.groups, group["group_id"]).get("enable", True) and enable:
                return 0
            try:
                await bot.send_group_msg(group_id=group["group_id"], message=message)
            except:
                pass
        await asyncio.sleep(interval)


async def broad_to_all_users(message: Message | str, white_list=None, black_list=None, enable=True, interval=0):
    """
        将消息广播到所有群聊
        白名单和黑名单只能选一个传入
        发生错误时跳到下一个

        :param interval: 相邻会话时间间隔
        :param enable: 仅在未屏蔽用户之间发送
        :param message:
        :param white_list: 白名单id
        :param black_list: 黑名单id
        :return:
        """
    banned_users = await Data(Data.globals, "liteyuki").get("banned_users", [])
    for bot_id in get_bots():
        bot: Bot = get_bot(bot_id)
        for friend in await bot.get_friend_list():
            if white_list is not None and friend["user_id"] not in white_list:
                return 0
            if black_list is not None and friend["user_id"] in black_list:
                return 0
            if friend["user_id"] in banned_users and enable:
                return 0
            try:
                await bot.send_private_msg(user_id=friend["user_id"], message=message)
            except:
                pass
        await asyncio.sleep(interval)
