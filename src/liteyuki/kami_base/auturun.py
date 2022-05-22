import os
from typing import Union, Optional, Dict, Any

from nonebot import get_driver
from nonebot.adapters import Bot
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
from nonebot.message import event_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.rule import to_me
from nonebot.typing import T_State

from extraApi.base import Log, ExtraData, ExConfig
# 日志记录和模式回复
from extraApi.rule import NOT_IGNORED, NOT_BLOCKED

driver = get_driver()


@driver.on_startup
async def folder_check():
    folders = [ExConfig.cache_path, ExConfig.data_path, ExConfig.data_backup_path, ExConfig.log_path]
    initial_config = {
        "kami.weather.key": "字符串，去和风天气申请key",
        "kami.weather.key_type": "字符串，和风天气key类型，商业版填写com，开发版填写dev",
        "kami.map.key": "字符串，去高德地图申请key",
        "kami.base.verify": False,  # bool值，是否启用邮箱验证，false的话kami.base.host_email, kami.base.auth, kami.base.host_user都不用填
        "kami.base.host_email": "字符串，发送验证码邮件的邮箱，建议注册一个163的",
        "kami.base.auth": "字符串，发送验证邮件的邮箱随机密码，可以在邮箱服务商处申请",
        "kami.base.host_user": "字符串，发送邮件的用户名，和邮箱的一致"
    }
    for folder in folders:
        if not os.path.exists(folder):
            os.makedirs(folder)
    initial_config: dict
    if not os.path.exists(os.path.join(ExConfig.data_path, "g0.json")):
        await ExtraData.createDatabase(targetType=ExtraData.Group, targetId=0, force=True, initialData=initial_config)
    else:
        g0_data = await ExtraData.get_global_data()
        for k, v in zip(initial_config.keys(), initial_config.values()):
            if k not in g0_data:
                g0_data[k] = v
        await ExtraData.setData(targetType=ExtraData.Group, targetId=0, key=None, value=g0_data, force=True)


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


# api记录
@Bot.on_called_api
async def record_api_calling(bot: Bot, exception: Optional[Exception], api: str, data: Dict[str, Any], result: Any):
    await Log.call_api_log(api, data, result)
