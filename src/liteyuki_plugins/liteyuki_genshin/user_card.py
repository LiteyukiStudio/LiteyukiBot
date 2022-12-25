import json
import os
import time

import aiohttp
from typing import Union
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.utils import run_sync

from .utils import *
from ...liteyuki_api.canvas import *
from ...liteyuki_api.config import Path
from ...liteyuki_api.data import Data
from ...liteyuki_api.utils import Command

user_card = on_command(cmd="面板", aliases={"原神数据", "更新面板", "更新数据", "#更新面板"})


@user_card.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    file_pool = {}
    for f in resource_pool.keys():
        if os.path.exists(os.path.join(Path.data, "genshin", f)):
            file_pool[f] = json.load(open(os.path.join(Path.data, "genshin", f), encoding="utf-8"))
        else:
            await user_card.finish(data_lost, at_sender=True)
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
    async with aiohttp.request("GET", url="https://enka.microgg.cn/u/%s" % uid) as resp:
        player_data = json.loads(await resp.text())
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
            hywh_font = os.path.join(Path.res, "fonts/hywh-85w.ttf")
            if not os.path.exists(hywh_font):
                await user_card.finish(data_lost)
            card.icon = Img(uv_size=(1, 1), box_size=(0.15, 0.15), parent_point=(0.04, 0.04), point=(0, 0),
                            img=Image.open(os.path.join(Path.cache, "genshin/%s.png" % iconName)))
            card.nickname = Text(uv_size=(1, 1), box_size=(0.8, 0.05), parent_point=(0.2, 0.04), point=(0, 0),
                                 text=playerInfo["nickname"],
                                 font=hywh_font, color=(0, 0, 0, 255))
            # uid
            if Data(Data.users, event.user_id).get_data(key="genshin.hid_uid", default=False):
                text_uid = str(uid)[0:3] + "*" * 6
            else:
                text_uid = str(uid)
            card.uid = Text(uv_size=(1, 1), box_size=(0.8, 0.03), parent_point=(0.95, 0.16), point=(1, 0),
                            text="UID:%s" % text_uid,
                            font=hywh_font, color=(60, 60, 60, 255))
            """冒险 世界等级"""
            card.level = Text(uv_size=(1, 1), box_size=(0.8, 0.035), parent_point=(0.2, 0.11), point=(0, 0),
                              text="%s    AR %s    WL %s" % (servers.get(str(uid)[0], "Unknown Server"), playerInfo["level"], playerInfo.get("worldLevel", 0)),
                              font=hywh_font, color=(80, 80, 80, 255))
            """签名"""
            card.sign = Text(uv_size=(1, 1), box_size=(0.8, 0.035), parent_point=(0.2, 0.16), point=(0, 0),
                             text=playerInfo.get("signature", ""),
                             font=hywh_font, color=(80, 80, 80, 255))
            """成就"""
            card.achievement = Text(uv_size=(1, 1), box_size=(0.4, 0.05), parent_point=(0.15, 0.27), point=(0, 0),
                                    text="%s：%s" % (info_lang.get(lang, info_lang["en"])["finishAchievementNum"], playerInfo.get("finishAchievementNum", 0)),
                                    font=hywh_font, color=(80, 80, 80, 255))
            """深境螺旋"""
            card.tower = Text(uv_size=(1, 1), box_size=(0.4, 0.05), parent_point=(0.85, 0.27), point=(1, 0),
                              text="%s：%s-%s" % (info_lang.get(lang, info_lang["en"])["tower"], playerInfo.get("towerFloorIndex", 0), playerInfo.get("towerLevelIndex", 0)),
                              font=hywh_font, color=(80, 80, 80, 255))
            """轻雪标记"""
            card.liteyuki_sign = Text(uv_size=(1, 1), box_size=(0.8, 0.04), parent_point=(0.5, 0.96), point=(0.5, 0.5),
                                      text=liteyuki_sign,
                                      font=hywh_font, color=(120, 120, 120, 255))
            if "showAvatarInfoList" not in playerInfo or len(playerInfo["showAvatarInfoList"]) == 0:
                card.tips = Text(uv_size=(4, 5), box_size=(3, 1), parent_point=(0.5, 0.6), point=(0.5, 0.5),
                                 text="请在游戏中至少展示一名角色", font=hywh_font, color=(120, 120, 120, 255))
            else:
                for i, character in enumerate(playerInfo["showAvatarInfoList"]):
                    # 公认数据
                    character_info = file_pool["characters_enka.json"].get(str(character["avatarId"]), {
                        "nameTextMapHash": 0,
                        "iconName": "Unknown",
                        "sideIconName": "Unknown",
                        "qualityType": "Unknown",
                        "costElemType": "Unknown"})
                    x = i % 4 * 0.24 + 0.14
                    y = 0.5 + i // 4 * 0.3
                    """单个角色图"""
                    character_card = Img(uv_size=(1, 1), box_size=(0.25, 0.25), parent_point=(x, y), point=(0.5, 0.5),
                                         img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % character_info["QualityType"])), keep_ratio=True)
                    element = elements[character_info["Element"]]
                    """角色正面头像材质名转化"""
                    character_icon = character_info["SideIconName"].replace("_Side", "")
                    if not os.path.exists(os.path.join(Path.data, "genshin", "ui", "%s.png" % character_icon)):
                        await run_sync(download_file)(url="https://enka.network/ui/%s.png" % character_icon,
                                                      file=os.path.join(Path.data, "genshin", "ui", "%s.png" % character_icon))
                    """角色头像图"""
                    character_card.icon = Img(uv_size=(4, 5), box_size=(3.6, 3.6), parent_point=(0.5, 0.4), point=(0.5, 0.5),
                                              img=Image.open(os.path.join(Path.data, "genshin", "ui", "%s.png" % character_icon)))
                    if character["avatarId"] not in [10000005, 10000007]:
                        """非旅行者角色元素图"""
                        character_card.element = Img(uv_size=(4, 5), box_size=(0.8, 0.8), parent_point=(0.11, 0.9), point=(0.5, 0.5),
                                                     img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % element)))
                    """角色等级文本"""
                    character_card.level = Text(uv_size=(4, 5), box_size=(4, 0.65), parent_point=(0.5, 0.9), point=(0.5, 0.5),
                                                text="Lv.%s" % character["level"], font=hywh_font, color=(0, 0, 0, 255))
                    card.__dict__["character_%s" % i] = character_card

            file = await run_sync(card.export_cache)()
            await user_card.send(MessageSegment.image(file="file:///%s" % file))
            await run_sync(card.delete)()
            if len(player_data.get("avatarInfoList", [])) > 0:
                player_data["time"] = tuple(list(time.localtime())[0:5])
                Data(Data.globals, "genshin_player_data").set_data(str(uid), player_data)
