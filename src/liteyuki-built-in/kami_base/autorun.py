import json
import os
from typing import Union, Optional, Dict, Any

import aiofiles
import aiohttp
from nonebot import get_driver

from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot, Message
from nonebot.message import event_preprocessor, run_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me, startswith
from nonebot.typing import T_State
from nonebot.exception import IgnoredException

from ...extraApi.base import Log, ExtraData, ExConfig, Command
# 日志记录和模式回复
from ...extraApi.rule import NOT_IGNORED, NOT_BLOCKED

driver = get_driver()


@driver.on_startup
async def folder_check():
    folders = [ExConfig.cache_path, ExConfig.data_path, ExConfig.data_backup_path, ExConfig.log_path, ExConfig.plugins_path, ExConfig.nonebot_plugin_path]
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
    initial_config: dict
    if not os.path.exists(os.path.join(ExConfig.data_path, "g0.json")):
        await ExtraData.createDatabase(targetType=ExtraData.Group, targetId=0, force=True)
    if not os.path.exists(os.path.join(ExConfig.res_path, "resource_database.json")):
        async with aiofiles.open(os.path.join(ExConfig.res_path, "resource_database.json"), "w", encoding="utf-8") as file:
            await file.write("{}")


@event_preprocessor
async def auto_log_receive_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    state2 = await ExtraData.get_global_data(key="enable_mode", default=1)
    if state2 == -1 and await (NOT_IGNORED & NOT_BLOCKED & to_me())(bot, event, state):
        if await SUPERUSER(bot, event):
            start = "[超级用户模式]"
        else:
            start = ""
        await bot.send(event, message="%s%s正在升级中" % (start, list(bot.config.nickname)[0]), at_sender=True)
    await Log.receive_message(bot, event)


@event_preprocessor
async def auto_filter_block_ignore(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    if not await NOT_BLOCKED(bot, event, state) or not await NOT_IGNORED(bot, event, state):
        raise IgnoredException("被屏蔽了")


@event_preprocessor
async def execute_preprocessor(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    """execute 处理器
    execute as=2751454815 msg
    execute only=bot_id列表 msg
    execute except=bot_id列表 msg
    """

    if await startswith("/execute")(bot, event, state):
        args, kwargs = Command.formatToCommand(event.raw_message)

        only_list = [int(uid) for uid in kwargs.get("only", str(bot.self_id)).split(",")]
        except_list = [int(uid) for uid in kwargs.get("except", "0").split(",")]
        if event.self_id in only_list and event.self_id not in except_list:
            pass
        else:
            raise IgnoredException("非指定bot")
        if await SUPERUSER(bot, event):
            event.user_id = int(kwargs.get("as", event.user_id))
            if isinstance(event, GroupMessageEvent): event.group_id = int(kwargs.get("at", event.group_id))
        delete_key = ["as", "at", "only", "except"]
        for k in delete_key:
            if k in kwargs:
                del kwargs[k]
        print(Command.formatToString(*args[1:], **kwargs))
        event.raw_message = Command.formatToString(*args[1:], **kwargs)
        print(event.raw_message)
        event.message = Message(event.raw_message)


# api记录
@Bot.on_called_api
async def record_api_calling(bot: Bot, exception: Optional[Exception], api: str, data: Dict[str, Any], result: Any):
    await Log.call_api_log(api, data, result)


@driver.on_bot_connect
async def check_for_update(bot: Bot):
    async with aiofiles.open(os.path.join(ExConfig.res_path, "version.json"), "r", encoding="utf-8") as version_file:
        now_version_data = json.loads(await version_file.read())
        now_version = now_version_data.get("version")
        now_version_description = now_version_data.get("description")
    async with aiohttp.request("GET", url="https://gitee.com/snowykami/Liteyuki/raw/master/resource/version.json") as resp:
        online_version = (json.loads(await resp.text()))["version"]
        if online_version != now_version:
            # 更新检查
            for superuser in bot.config.superusers:
                await bot.send_private_msg(user_id=int(superuser), message="检测到更新：%s -> %s" % (now_version, online_version))
