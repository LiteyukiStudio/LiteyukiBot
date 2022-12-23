import json
import os
import aiohttp
from typing import Union
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.utils import run_sync

from .utils import *
from ...liteyuki_api.canvas import *
from ...liteyuki_api.config import Path
from ...liteyuki_api.data import Data
from ...liteyuki_api.utils import Command

user_card = on_command(cmd="面板", aliases={"原神数据"})


@user_card.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    file_pool = {}
    for f in resource_pool.keys():
        if os.path.exists(os.path.join(Path.data, "genshin", f)):
            file_pool[f] = json.load(open(os.path.join(Path.data, "genshin", f), encoding="utf-8"))
        else:
            await user_card.finish(data_lost)
    args, kwargs = Command.formatToCommand(str(args).strip())
    db = Data(Data.users, event.user_id)
    lang = kwargs.get("lang", db.get_data(key="genshin.lang", default="zh-CN"))
    uid = 0

    if args[0] == "" and db.get_data(key="genshin.uid", default=None) is None:
        await user_card.finish("命令参数中未包含uid且未绑定过uid", at_sender=True)
    if len(args) >= 1 and args[0] != "":
        if not args[0].isdigit():
            await user_card.finish("命令参数uid格式有误", at_sender=True)
        else:
            uid = int(args[0])
    else:
        uid = db.get_data(key="genshin.uid", default=None)

    async with aiohttp.request("GET", url="https://enka.network/u/%s/__data.json" % uid) as resp:
        player_data = await resp.json()
        servers = {
            "1": "天空岛",
            "2": "天空岛",
            "5": "世界树",
            "6": "America",
            "7": "Europe",
            "8": "Asia",
            "9": "TW,HK,MO"
        }
        info_lang = {
            "zh-CN": {
                "finishAchievementNum": "成就数",
                "tower": "深境螺旋"
            },
            "zh-TW": {
                "finishAchievementNum": "成就数",
                "tower": "深境螺旋"
            },
            "en": {
                "finishAchievementNum": "Achievements",
                "tower": "Spiral Abyss"
            },
        }
        if "playerInfo" not in player_data:
            await user_card.finish("uid信息不存在", at_sender=True)
        else:
            playerInfo = player_data["playerInfo"]
            card = Canvas(Image.open(os.path.join(Path.res, "textures", "genshin", "stats_bg.png")))
            """头像的角色id"""
            icon_avatar_id = player_data["playerInfo"]["profilePicture"]["avatarId"]
            """头像材质名称"""
            iconName = file_pool["characters.json"].get(str(icon_avatar_id), {"iconName": "unknown"})["iconName"]
            await run_sync(resource_detect)(iconName)
            """检测字体"""
            hywh_font = os.path.join(Path.res, "fonts/hywh.ttf")
            if not os.path.exists(hywh_font):
                await user_card.finish(data_lost)
            card.icon = Img(uv_size=(1, 1), box_size=(0.15, 0.15), parent_point=(0.04, 0.04), point=(0, 0), img=Image.open(os.path.join(Path.cache, "genshin", "ui", "%s.png" % iconName)))
