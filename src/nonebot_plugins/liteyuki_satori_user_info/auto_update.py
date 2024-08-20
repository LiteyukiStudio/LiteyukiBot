import nonebot

from nonebot.message import event_preprocessor
from src.utils.base.ly_typing import T_MessageEvent
from src.utils import satori_utils
from nonebot.adapters import satori
from nonebot_plugin_alconna.typings import Event
from src.nonebot_plugins.liteyuki_status.counter_for_satori import satori_counter


@event_preprocessor
async def pre_handle(event: Event):
    if isinstance(event, satori.MessageEvent):
        if event.user.id == event.self_id:
            satori_counter.msg_sent += 1
        else:
            satori_counter.msg_received += 1
        if event.user.name is not None:
            if await satori_utils.user_infos.put(event.user):
                nonebot.logger.info(f"Satori user {event.user.name}<{event.user.id}> updated")
