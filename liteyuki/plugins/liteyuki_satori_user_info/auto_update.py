from liteyuki.utils import satori_utils
from nonebot.message import event_preprocessor
# from nonebot_plugin_alconna.typings import Event
from liteyuki.utils.base.ly_typing import T_MessageEvent
from liteyuki.utils import satori_utils
from nonebot.adapters import satori
from nonebot_plugin_alconna.typings import Event


@event_preprocessor
async def pre_handle(event: Event):
    print("UPDATE_USER")
    if isinstance(event, satori.MessageEvent):
        if event.user.name is not None:
            await satori_utils.user_infos.put(event.user)
            print(event.user)
