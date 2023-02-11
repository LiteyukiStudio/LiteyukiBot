import json
import os
import time
from typing import List, Dict, Any, Union

import requests
from pydantic import BaseModel

from ...liteyuki_api.config import Path
from ...liteyuki_api.data import Data
from ...liteyuki_api.utils import download_file


class ProfilePicture(BaseModel):
    avatarId: int = 0


class ShowAvatar(BaseModel):
    avatarId: int = 0
    level: int = 0


class PlayerInfo(BaseModel):
    nickname: str = ""
    level: int = 0
    worldLevel: int = 0
    nameCardId: int = 0
    finishAchievementNum: int = 0
    towerFloorIndex: int = 0
    towerLevelIndex: int = 0
    signature: str = ""
    showAvatarInfoList: List[ShowAvatar] = [ShowAvatar()]
    showNameCardIdList: List[int] = 0
    profilePicture: ProfilePicture = ProfilePicture()


class Prop(BaseModel):
    type: int = 0,
    ival: str = "",
    val: str = ""


class EquipStat(BaseModel):
    mainPropId: str = ""
    appendPropId: str = ""
    statValue: Any = 0.0


class Reliquary(BaseModel):
    level: int = 0
    mainPropId: int = 0
    appendPropIdList: List[int] = [0]


class Weapon(BaseModel):
    level: int = 0,
    promoteLevel: int = 0
    affixMap: Dict[str, int] = {"": 0}


class EquipFlat(BaseModel):
    nameTextMapHash: str = ""
    setNameTextMapHash: str = ""
    rankLevel: int = 0
    reliquaryMainstat: EquipStat = EquipStat()
    reliquarySubstats: List[EquipStat] = [EquipStat()]
    weaponStats: List[EquipStat] = [EquipStat()]
    itemType: str = ""
    icon: str = ""
    equipType: str = ""


class Equip(BaseModel):
    itemId: int = 0
    flat: EquipFlat = EquipFlat()
    reliquary: Reliquary = Reliquary()
    weapon: Weapon = Weapon()

class FetterInfo(BaseModel):
    expLevel: int = 0

class Avatar(BaseModel):
    avatarId: int = 0
    propMap: Dict[str, Prop] = {"": Prop()}
    talentIdList: List[int] = []
    fightPropMap: Dict[str, Any] = {"": 0}
    skillDepotId: int = 0
    inherentProudSkillList: List[int] = [0]
    skillLevelMap: Dict[str, int]
    proudSkillExtraLevelMap: Dict[str, int] = {"": 0}
    equipList: List[Equip] = [Equip()]
    fetterInfo: FetterInfo = FetterInfo()


class PlayerData(BaseModel):
    playerInfo: PlayerInfo = None
    avatarInfoList: List[Avatar] = None
    ttl: int = 0
    uid: str = ""
    update_time: list = list(time.localtime())[0:6]


def get_online_player_data_by_uid(uid: int) -> PlayerData:
    """
    通过uid从Enka网络获取信息

    :param uid:
    :return:
    """
    r = requests.get(url=f"https://enka.network/u/{uid}/__data.json")
    json.dump(r.json(), open("rq.json", "w", encoding="utf-8"), indent=4, ensure_ascii=False)
    return PlayerData(**r.json())


def get_server_name_by_uid(uid: str) -> str:
    """
    通过判断uid开头来判断服务器，暂且可以这样

    :param uid:
    :return:
    """
    server_map = {
        "1": "天空岛",
        "2": "天空岛",
        "3": "未来天空岛",
        "4": "未来天空岛",
        "5": "世界树",
        "6": "America",
        "7": "Europe",
        "8": "Asia",
        "9": "TW,HK,MO"
    }
    return server_map.get(str(uid)[0], "Unknown")

def get_greece_element_name_by_english(en_name: str):
    elements = {
        "Rock": "geo",  # 岩元素
        "Wind": "Anemo",  # 风元素
        "Water": "Hydro",  # 水元素
        "Electric": "Electro",  # 雷元素
        "Fire": "Pyro",  # 火元素
        "Ice": "Cryo",  # 冰元素
        "Grass": "Dendro",  # 草元素
        "Unknown": "Unknown"  # 万能元素
    }
    return elements.get(en_name, "")


def get_text_by_lang(key: str, lang: str = "en", loc=None) -> str:
    """通过HashId在HashMap获取对应语言的文本"""
    if loc is None:
        loc = {}
    return loc.get(lang, loc["en"]).get(key, "Id not existing")


def detect_enka_texture(texture: str):
    """
    enka资源检测下载器
    若欲分离此代码请自行编写该函数

    :param texture:
    :return:
    """
    fp = os.path.join(Path.data, f"enka/texture/{texture}.png")
    if not os.path.exists(fp):
        """此处调用了轻雪下载接口，若欲将代码分离出请自行编写下载部分"""
        download_file(url="https://enka.network/ui/%s.png" % texture,
                      file=fp)
    else:
        pass


def get_local_player_data_by_uid(uid: int) -> PlayerData:
    player_data: PlayerData = PlayerData(**await Data(Data.globals, "genshin_player_data").get(str(uid), {}))
    return player_data


def update_local_player_info_by_uid(uid: int):
    """
    更新本地角色面板，原有角色也会保留

    :param uid:
    :return:
    """
    last_player_data = get_online_player_data_by_uid(uid)

    stored_player_data = get_local_player_data_by_uid(uid)
    stored_avatar_id_list = (avatar.avatarId for avatar in stored_player_data.avatarInfoList)
    stored_avatar_map: Dict[int, Avatar] = dict(zip(stored_avatar_id_list, stored_player_data.avatarInfoList))

    for last_avatar in last_player_data.avatarInfoList:
        stored_avatar_map[last_avatar.avatarId] = last_avatar
    stored_player_data.avatarInfoList = stored_avatar_map.values()
    stored_player_data.update_time = last_player_data.update_time
    stored_player_data.playerInfo = last_player_data.playerInfo
    await Data(Data.globals, "genshin_game_data").set(str(uid), stored_player_data.json())
