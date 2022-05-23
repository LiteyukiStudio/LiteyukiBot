from typing import Union

from nonebot.permission import SUPERUSER

from extraApi.plugin import *
from extraApi.base import ExtraData, Balance, Session

from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.rule import Rule
from nonebot.typing import T_State


def plugin_enable(pluginId: str):
    """
    :param pluginId: 插件id
    :return:
    """

    async def _pluginEnable(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
        bannedPlugin = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                               key="banned_plugin", default=list())
        enabledPlugin = await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event),
                                                key="enabled_plugin", default=list())
        # 群聊授权或私聊授权
        if await ExtraData.getData(targetType=event.message_type, targetId=ExtraData.getTargetId(event), key="enable", default=False) or await ExConfig.gmi(event):
            pass
        else:
            return False
        plugin = searchForPlugin(pluginId)
        if plugin is None:
            await Session.sendExceptionToSuperuser(bot, event, state, exception=BaseException("插件id:%s不存在，请检查代码中是否输入正确" % pluginId))
            return False
        if plugin.defaultStats and plugin.pluginId not in bannedPlugin or not plugin.defaultStats and plugin.pluginId in enabledPlugin:
            return True
        else:
            return False

    return Rule(_pluginEnable)


def minimumCoin(num: Union[float, int], reason=None) -> Rule:
    async def _minimumCoin(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
        prompt = state.get("balance_prompt", False)

        coin = await Balance.getCoinValue(user_id=event.user_id)
        if coin >= num:
            return True
        else:
            if not prompt and reason is not None:
                await bot.send(event, "硬币余额不足：%s" % coin, at_sender=True)
                state["balance_prompt"] = True
            return False

    return Rule(_minimumCoin)


@Rule
async def MODE_DETECT(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    """
    模式判断

    :param bot:
    :param event:
    :param state:
    :return:
    """
    enable_mode = await ExtraData.get_global_data(key="enable_mode", default=1)
    if enable_mode == 1:
        return True
    elif enable_mode == 0:
        return False
    elif enable_mode == -1:
        if await SUPERUSER(bot, event):
            return True
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


@Rule
async def NOT_IGNORED(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    """
    仅在用户可以响应时返回true

    :param bot:
    :param event:
    :param state:
    :return:
    """
    no_response = await ExtraData.get_global_data(key="ignored_users", default=[])
    if event.user_id in no_response:
        return False
    else:
        return True


@Rule
async def NOT_BLOCKED(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    """
    仅在用户可以响应时返回true

    :param bot:
    :param event:
    :param state:
    :return:
    """
    no_response = await ExtraData.get_global_data(key="blocked_users", default=[])
    if event.user_id in no_response:
        return False
    else:
        return True
