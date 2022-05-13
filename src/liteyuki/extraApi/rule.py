from typing import Union

from nonebot.permission import SUPERUSER

from extraApi.plugin import *
from extraApi.base import ExtraData, Balance, Session
from extraApi.permission import AUTHUSER
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.internal.rule import Rule
from nonebot.typing import T_State


def pluginEnable(pluginId: str):
    async def _pluginEnable(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
        enable_mode = await ExtraData.get_global_data(key="enable_mode", default=1)
        # 1正常状态 0停止状态 -1检修模式仅响应检修成员
        no_response = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                              key="no_response", default=list())
        bannedPlugin = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                               key="banned_plugin", default=list())
        enabledPlugin = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                                key="enabled_plugin", default=list())
        test_users = await ExtraData.get_global_data(key="test_users", default=[])

        plugin = searchForPlugin(pluginId)
        # 不响应名单
        if event.user_id in no_response:
            return False

        # 模式检测
        if enable_mode == 0:
            return False

        if enable_mode == -1 and not (event.user_id in test_users or await SUPERUSER(bot, event)):
            return False

        if plugin is None:
            await Session.sendExceptionToSuperuser(bot, event, state, exception=BaseException("插件id:%s不存在，请检查代码中是否输入正确" % pluginId))
            return False
        if plugin.defaultStats and plugin.pluginId not in bannedPlugin or not plugin.defaultStats and plugin.pluginId in enabledPlugin:
            return True
        else:
            return False

    return Rule(_pluginEnable)


def minimumCoin(num: Union[float, int]) -> Rule:
    async def _minimumCoin(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
        coin = await Balance.getCoinValue(user_id=event.user_id)
        if coin >= num:
            return True
        else:
            return False

    return Rule(_minimumCoin)


@Rule
async def AUTHGROUP(bot: Bot, event: GroupMessageEvent, state: T_State):
    if type(event) is GroupMessageEvent:
        auth = await ExtraData.getData(targetType=ExtraData.Group, targetId=event.group_id, key="enable", default=False)
        return auth
    else:
        return False


@Rule
async def BOT_IS_ADMIN(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    机器人为管理员是规则生效，匹配群主
    :param bot:
    :param event:
    :param state:
    :return:
    """
    role = (await bot.get_group_member_info(group_id=event.group_id, user_id=event.self_id))["role"]
    if role in ["admin", "owner"]:
        return True
    else:
        return False


@Rule
async def BOT_IS_OWNER(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    机器人是群主是规则生效，不匹配管理员
    :param bot:
    :param event:
    :param state:
    :return:
    """
    role = (await bot.get_group_member_info(group_id=event.group_id, user_id=event.self_id))["role"]
    if role in ["owner"]:
        return True
    else:
        return False


@Rule
async def BOT_GT_USER(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    群聊bot权限高于用户权限
    :param bot:
    :param event:
    :param state:
    :return:
    """
    if type(event) is GroupMessageEvent:
        botRole = (await bot.get_group_member_info(group_id=event.group_id, user_id=event.self_id))["role"]
        userRole = (await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id))["role"]
        if botRole == "owner":
            return True
        elif botRole == "admin" and userRole == "member":
            return True
        else:
            return False
    else:
        return False


@Rule
async def BOT_GE_USER(bot: Bot, event: GroupMessageEvent, state: T_State):
    """
    群聊bot权限高于或等于用户权限
    :param bot:
    :param event:
    :param state:
    :return:
    """
    if type(event) is GroupMessageEvent:
        botRole = await bot.get_group_member_info(group_id=event.group_id, user_id=event.self_id)
        userRole = await bot.get_group_member_info(group_id=event.group_id, user_id=event.user_id)
        if botRole == "owner":
            return True
        elif botRole == "admin" and userRole in ["member", "admin"]:
            return True
        elif botRole == userRole:
            return True
        else:
            return False
    else:
        return False
