import copy
import random
from typing import Type

from PIL import ImageEnhance
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.internal.matcher import Matcher
from nonebot.utils import run_sync

from .enka_api import *
from .utils import wish_img_crop
from ...liteyuki_api.canvas import *
from ...liteyuki_api.utils import Command, clamp, generate_signature


async def character_card_handle(matcher: Type[Matcher], event: MessageEvent):
    args, kwargs = Command.formatToCommand(event.raw_message)
    character_name_input = " ".join(args).strip().replace("面板", "").replace("#", "")
    if character_name_input == "更新":
        raise IgnoredException("此为更新所有原神角色数据")
    lang = kwargs.get("lang", "zh-CN")
    hash_id = await run_sync(get_hash_id_by_search)(character_name_input)
    avatar_id = await run_sync(get_avatar_id_by_hash_id)(hash_id)
    local_player_data: PlayerData = await run_sync(get_local_player_data_by_uid)(220587800)
    for avatar in local_player_data.avatarInfoList:
        if str(avatar.avatarId) == str(avatar_id):
            canvas: Canvas = await run_sync(generate_character_card)(local_player_data, avatar, lang)
            await matcher.finish(MessageSegment.image(file=f"file:///{await run_sync(canvas.export_cache)()}"))


def get_hash_id_by_search(keyword: str) -> str | None:
    """
    在hashmap和别称map中搜索角色名hashId，若不存在则为None
    :param keyword:
    :return:
    """
    hash_map = json.load(open(os.path.join(Path.res, "genshin/loc.json"), encoding="utf-8"))
    for lang, lang_data in hash_map.items():
        for hash_id, text in lang_data.items():
            if keyword == text:
                return str(hash_id)
    else:
        """从别称数据中查找hash_id"""
        for hash_id, aliases_list in (await Data(Data.globals, "genshin_game_data").get(key="character_aliases", default={})).items():
            if keyword in aliases_list:
                return str(hash_id)


def get_avatar_id_by_hash_id(hash_id: str) -> str | None:
    character_map = json.load(open(os.path.join(Path.res, "genshin/characters_enka.json")))
    for avatar_id, avatar_data in character_map.items():
        if str(avatar_data["NameTextMapHash"]) == hash_id:
            return avatar_id


def get_hash_id_by_avatar_id(avatar_id: str) -> str | None:
    character_map = json.load(open(os.path.join(Path.res, "genshin/characters_enka.json")))
    return character_map.get(avatar_id, {"NameTextMapHash": None})["NameTextMapHash"]


def get_enka_avatar_resource_by_avatar_id(avatar_id: str) -> dict | None:
    character_map = json.load(open(os.path.join(Path.res, "genshin/characters_enka.json")))
    return character_map.get(avatar_id, None)


def generate_character_card(playerData: PlayerData, avatar: Avatar, lang: str):
    rank_level = {
        0: 20,
        1: 40,
        2: 50,
        3: 60,
        4: 70,
        5: 80,
        6: 90
    }
    percent_prop = [
        "FIGHT_PROP_PHYSICAL_ADD_HURT",
        "FIGHT_PROP_CHARGE_EFFICIENCY",
        "FIGHT_PROP_HEAL_ADD",
        "FIGHT_PROP_ATTACK_PERCENT",
        "FIGHT_PROP_HP_PERCENT",
        "FIGHT_PROP_DEFENSE_PERCENT",
        "FIGHT_PROP_CRITICAL",
        "FIGHT_PROP_CRITICAL_HURT",
        "FIGHT_PROP_FIRE_ADD_HURT",
        "FIGHT_PROP_WATER_ADD_HURT",
        "FIGHT_PROP_WIND_ADD_HURT",
        "FIGHT_PROP_ICE_ADD_HURT",
        "FIGHT_PROP_ROCK_ADD_HURT",
        "FIGHT_PROP_ELEC_ADD_HURT",
        "FIGHT_PROP_GRASS_ADD_HURT"
    ]
    fight_prop = avatar.fightPropMap
    prop_dict = {
        "FIGHT_PROP_MAX_HP": {
            "type": "int1",
            "base": fight_prop["1"],
            "add": fight_prop["2000"] - fight_prop["1"],
            "value": fight_prop["2000"]
        },
        "FIGHT_PROP_ATTACK": {
            "type": "int1",
            "base": fight_prop["4"],
            "add": fight_prop["2001"] - fight_prop["4"],
            "value": fight_prop["2001"]
        },
        "FIGHT_PROP_DEFENSE": {
            "type": "int1",
            "base": fight_prop["7"],
            "add": fight_prop["2002"] - fight_prop["7"],
            "value": fight_prop["2002"]
        },
        "FIGHT_PROP_ELEMENT_MASTERY": {
            "type": "int2",
            "value": fight_prop["28"]
        },
        "FIGHT_PROP_CRITICAL": {
            "type": "percent",
            "accuracy": 1,
            "value": fight_prop["20"]
        },
        "FIGHT_PROP_CRITICAL_HURT": {
            "type": "percent",
            "accuracy": 1,
            "value": fight_prop["22"]
        },
        "FIGHT_PROP_CHARGE_EFFICIENCY": {
            "type": "percent",
            "accuracy": 1,
            "value": fight_prop["23"]
        },
    }
    addition_props = {
        30: "FIGHT_PROP_PHYSICAL_ADD_HURT",
        41: "FIGHT_PROP_ELEC_ADD_HURT",
        42: "FIGHT_PROP_WATER_ADD_HURT",
        43: "FIGHT_PROP_GRASS_ADD_HURT",
        44: "FIGHT_PROP_WIND_ADD_HURT",
        45: "FIGHT_PROP_ROCK_ADD_HURT",
        46: "FIGHT_PROP_ICE_ADD_HURT",
        26: "FIGHT_PROP_HEAL_ADD",  # 治疗
        40: "FIGHT_PROP_FIRE_ADD_HURT",
    }
    times = 0

    max_value = max([fight_prop[str(fight_prop_id)] for fight_prop_id in addition_props])
    for t_i in range(len(addition_props)):
        for fight_prop_id, fight_prop_name in copy.deepcopy(addition_props).items():
            if fight_prop[str(fight_prop_id)] == max_value and max_value > 0:
                times += 1
                prop_dict[fight_prop_name] = {
                    "type": "percent",
                    "accuracy": 1,
                    "value": fight_prop[str(fight_prop_id)]
                }
                del addition_props[fight_prop_id]
            max_value = max([fight_prop[str(fight_prop_id)] for fight_prop_id in addition_props])
            if times >= 2 or max_value == 0:
                break
    artifact_set_dict = {}
    """一件套圣遗物列表"""
    sacrificer = [
        "212557731",
        "262428003",
        "287454963",
        "2060049099",
        "3999792907"
    ]

    artifacts: List[Reliquary()] = []
    weapon = Weapon()

    for equip in avatar.equipList:
        if equip.flat.itemType == "ITEM_RELIQUARY":
            artifacts.append(equip)
        else:
            weapon = equip

    enkaAvatarResource = get_enka_avatar_resource_by_avatar_id(avatar.avatarId.__str__())
    greece_element = get_greece_element_name_by_english(enkaAvatarResource["Element"])
    nameTextHash = get_hash_id_by_avatar_id(avatar.avatarId.__str__())

    base_fillet = 5
    font_hywh = os.path.join(Path.res, "fonts/hywh-85w.ttf")
    loc_data = json.load(open(os.path.join(Path.res, "genshin/loc.json"), encoding="utf-8"))
    chinese_name = loc_data["zh-CN"][nameTextHash.__str__()]
    if os.path.exists(os.path.join(Path.res, "textures", "genshin", f"{chinese_name}.png")):
        character_wish_img = Image.open(os.path.join(Path.res, "textures", "genshin", f"{chinese_name}.png"))
        character_wish_img = wish_img_crop(character_wish_img)
    else:
        character_wish_img = Image.new("RGBA", (300, 300), color=(255, 255, 255, 255))
    detect_enka_texture(enkaAvatarResource["SideIconName"].split("_")[-1])

    """大画布 | 渲染部分"""
    canvas = Canvas(Image.new(mode="RGBA", size=(1080, 2400), color=(127, 127, 127, 255)))
    """分割"""
    canvas.part_1 = Panel(uv_size=(1, 1), box_size=(1, 1 / 3), parent_point=(0, 0), point=(0, 0))
    canvas.part_2 = Panel(uv_size=(1, 1), box_size=(1, 1 / 3), parent_point=(0, 1 / 3), point=(0, 0))
    canvas.part_3 = Panel(uv_size=(1, 1), box_size=(1, 1 / 3), parent_point=(0, 2 / 3), point=(0, 0))
    """Part-1"""
    """角色立绘，命座，天赋，名称，等级，好感度"""
    canvas.part_1.avatar_img = Img(uv_size=(1, 1), box_size=(2, 1.0), parent_point=(0.5, 0.55), point=(0.5, 0.5), img=character_wish_img)
    canvas.part_1.name = Text(uv_size=(1, 1), box_size=(0.66, 0.06), parent_point=(0.03061 * 3, 0.04),
                              point=(0, 0), text=get_text_by_lang(str(nameTextHash), lang, loc_data), font=font_hywh)
    name_pos = canvas.get_parent_box("part_1.name")
    """等级基础值"""
    canvas.part_1.level = Text(uv_size=(1, 1), box_size=(0.9, 0.04), parent_point=(0.03061 * 3, name_pos[3] + 0.02), point=(0, 0),
                               text=f'{get_text_by_lang("level", lang, loc_data)} {avatar.propMap["4001"].val}/{rank_level[int(avatar.propMap["1002"].val)]}',
                               font=font_hywh, force_size=True)
    level_pos = canvas.get_parent_box("part_1.level")

    canvas.part_1.love_icon = Img(uv_size=(1, 1), box_size=(0.9, 0.05), parent_point=(0.0306 * 3, level_pos[3] + 0.01),
                                  point=(0, 0), img=Image.open(os.path.join(Path.res, "textures", "genshin", "love.png")))
    love_icon_pos = canvas.get_parent_box("part_1.love_icon")
    canvas.part_1.love_level = Text(uv_size=(1, 1), box_size=(0.9, 0.04), parent_point=(love_icon_pos[2] + 0.02, (love_icon_pos[1] + love_icon_pos[3]) / 2),
                                    point=(0, 0.6),
                                    text=str(avatar.fetterInfo.expLevel),
                                    font=font_hywh)
    """元素图"""
    canvas.part_1.element_icon = Img(uv_size=(1, 1), box_size=(0.9, 0.08), parent_point=(0.2959 * 3, 0.16),
                                     point=(0.5, 0.5), img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % greece_element)))
    """命之座部分"""
    constellation_distance = 0.1
    x0 = 0.045 * 3
    y0 = 0.38
    base_size = 0.12
    texture_size = 0.064
    constellation_num = len(avatar.talentIdList)
    for i, constellation_texture_name in enumerate(enkaAvatarResource["Consts"]):
        detect_enka_texture(constellation_texture_name)
        if i + 1 <= constellation_num:
            # 已解锁命之座,先放底图，再放材质图
            canvas.part_1.__dict__[f"base_{i}"] = Img(uv_size=(1, 1), box_size=(0.3, base_size), parent_point=(x0, y0 + i * constellation_distance),
                                                      point=(0.5, 0.5),
                                                      img=Image.open(os.path.join(Path.res, "textures", "genshin", "constellation_%s_unlocked.png" % greece_element)))
            canvas.part_1.__dict__[f"const_{i}"] = Img(uv_size=(1, 1), box_size=(0.3, texture_size), parent_point=(x0, y0 + i * constellation_distance),
                                                       point=(0.5, 0.5),
                                                       img=Image.open(os.path.join(Path.cache, "genshin", f"{constellation_texture_name}.png")))
        else:
            # 未解锁命之座 先放材质图，再放底图遮盖，最后加锁
            texture_img = ImageEnhance.Brightness(
                Image.open(os.path.join(Path.cache, "genshin", "%s.png" % constellation_texture_name)).convert("RGBA")).enhance(0.5)
            base_img = ImageEnhance.Brightness(
                Image.open(os.path.join(Path.res, "textures", "genshin", "constellation_%s_locked.png" % greece_element)).convert("RGBA")).enhance(0.75)
            canvas.part_1.__dict__[f"const_{i}"] = Img(uv_size=(1, 1), box_size=(0.3, base_size), parent_point=(x0, y0 + i * constellation_distance),
                                                       point=(0.5, 0.5),
                                                       img=base_img)
            canvas.part_1.__dict__[f"base_{i}"] = Img(uv_size=(1, 1), box_size=(0.3, texture_size), parent_point=(x0, y0 + i * constellation_distance),
                                                      point=(0.5, 0.5),
                                                      img=texture_img)
            canvas.part_1.__dict__[f"lock_{i}"] = Img(uv_size=(1, 1), box_size=(0.3, 0.032), parent_point=(x0, y0 + i * constellation_distance),
                                                      point=(0.5, 0.5),
                                                      img=Image.open(os.path.join(Path.res, "textures", "genshin", "locked.png")))

    """P1天赋部分"""
    x0 = 0.2959 * 3
    y0 = 0.58
    skill_distance = 0.14
    """遍历三个天赋"""
    for skill_i, skill_data in enumerate(enkaAvatarResource["Skills"].items()):
        skill_id = skill_data[0]
        skill_texture = skill_data[1]
        detect_enka_texture(skill_texture)
        skill_level = avatar.skillLevelMap[skill_id]
        add = False
        if skill_i == 1 and constellation_num >= 3:
            skill_level += 3
            add = True
        if skill_i == 2 and constellation_num >= 5:
            skill_level += 3
            add = True
        """天赋底图"""
        canvas.part_1.__dict__[f"skill_base_{skill_i}"] = Img(uv_size=(1, 1), box_size=(0.3, 0.12), parent_point=(x0, y0 + skill_i * skill_distance),
                                                                point=(0.5, 0.5),
                                                                img=Image.open(os.path.join(Path.res, "textures", "genshin", "talent.png")))
        """天赋图"""
        canvas.part_1.__dict__[f"talent_{skill_i}"] = Img(uv_size=(1, 1), box_size=(0.1, 0.08), parent_point=(x0, y0 + skill_i * skill_distance),
                                                            point=(0.5, 0.5),
                                                            img=Image.open(os.path.join(Path.cache, "genshin", f"{skill_texture}.png")))
        talent_base_pos = canvas.get_parent_box(f"part_1.skill_base_{skill_i}")
        """天赋等级底图"""
        talent_base = canvas.part_1.__dict__[f"talent_level_base_{skill_i}"] = \
            Img(uv_size=(1, 1), box_size=(0.1, 0.03), parent_point=((talent_base_pos[0] + talent_base_pos[2]) / 2 * 3, talent_base_pos[3]), point=(0.5, 1),
                img=Image.open(os.path.join(Path.res, f'textures/genshin/talent_level_base_{("add" if add else "normal")}.png')))

        """命之座加成为蓝色等级数字"""
        if add and skill_level == 13 or not add and skill_level == 10:
            color = Color.hex2dec("FFFFEE00")
        else:
            color = (255, 255, 255, 255)
        """天赋等级"""
        talent_base.level = Text(uv_size=(1, 1), box_size=(1.5, 0.8),
                                 parent_point=(0.5, 0.5),
                                 point=(0.5, 0.5), text=str(skill_level), font=font_hywh, color=color, force_size=True)

    """武器部分"""
    # 武器图

    start_line_x = 0.016938 * 3
    star = weapon.flat.rankLevel
    """武器贴图缓存检测"""
    detect_enka_texture(weapon.flat.icon)
    """武器贴图"""
    canvas.part_2.weapon_icon = Img(uv_size=(1, 1), box_size=(0.54, 0.25), parent_point=(start_line_x, 0.06),
                                    point=(0, 0), img=Image.open(os.path.join(Path.cache, "genshin", "%s.png" % weapon.flat.icon)))
    """武器贴图位置"""
    weapon_pos = canvas.get_parent_box("part_2.weapon_icon")
    canvas.part_2.weapon_icon.weapon_bar = Img(
        uv_size=(1, 1), box_size=(1, 0.25), parent_point=(0.5, 1),
        point=(0.5, 0.5), img=Image.open(os.path.join(Path.res, "textures/genshin/weapon_bar_star_%s.png" % star))
    )
    """武器名"""
    canvas.part_2.weapon_name = Text(uv_size=(1, 1), box_size=(0.6, 0.05), parent_point=(weapon_pos[2] + 0.06, weapon_pos[1]),
                                     point=(0, 0), text=get_text_by_lang(weapon.flat.nameTextMapHash, lang, loc=loc_data), font=font_hywh)

    """武器星级"""
    canvas.part_2.weapon_star = Img(uv_size=(1, 1), box_size=(0.25, 0.04), parent_point=((weapon_pos[0] + weapon_pos[2]) / 2, weapon_pos[3]),
                                    point=(0.5, 1), img=Image.open(os.path.join(Path.res, "textures/genshin/star_%s.png" % star)))

    """武器属性部分，武器属性底图"""
    canvas.part_2.weapon_info = Rectangle(uv_size=(1, 1), box_size=(0.4593, 0.155), parent_point=(0.4898, (weapon_pos[3] + weapon_pos[1]) / 2.4),
                                          point=(0, 0), color=(0, 0, 0, 80), fillet=base_fillet)
    # 武器属性图上的内容锚点坐标
    x0 = 0.075
    y0 = 0.25
    y1 = 0.75

    for i, stats in enumerate(weapon.flat.weaponStats):
        canvas.part_2.weapon_info.__dict__[f"prop_icon_{i}"] = Img(uv_size=(1, 1), box_size=(0.22, 0.21), parent_point=(x0, y0),
                                                                   point=(0, 0.5),
                                                                   img=Image.open(os.path.join(Path.res, "textures/genshin/%s.png" % stats.appendPropId)))
        icon_pos = canvas.get_parent_box(f"part_2.weapon_info.prop_icon_{i}")

        if stats.appendPropId in percent_prop:
            value = str(stats.statValue) + "%"
        else:
            value = str(stats.statValue)
        canvas.part_2.weapon_info.__dict__[f"prop_value_{i}"] = Text(uv_size=(1, 1), box_size=(0.5, 0.21), parent_point=(icon_pos[2] + 0.03, y0),
                                                                     point=(0, 0.5), text=value, font=font_hywh, force_size=True)
        value_pos = canvas.get_parent_box(f"part_2.weapon_info.prop_value_{i}")
        x0 = value_pos[2] + 0.06

    """武器等级"""
    x0 = 0.075
    canvas.part_2.weapon_info.level = Text(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=(x0, y1),
                                           point=(0, 0.5),
                                           text=
                                           f'{get_text_by_lang("level", lang, loc_data)}/{weapon.weapon.level}/{rank_level[weapon.weapon.promoteLevel]}',
                                           font=font_hywh, force_size=True)
    refine = 0
    if "affixMap" in weapon.weapon:
        for v in weapon.weapon.affixMap.values():
            refine = v
    else:
        refine = 0
    """精炼度"""
    canvas.part_2.weapon_info.refine = Text(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=(1 - x0, y1),
                                            point=(1, 0.5),
                                            text="R%s" % (refine + 1),
                                            font=font_hywh, force_size=True, color=Color.hex2dec("FFFFEE00" if refine == 4 else "FFFFFFFF"))
    line = 0
    prop_line_distance = 0.053
    prop_start_y = weapon_pos[3] + 0.04
    alpha = 80
    """角色详细属性部分"""
    """属性浅色底图"""
    canvas.part_2.prop_base = Rectangle(uv_size=(1, 1), box_size=(0.95, prop_line_distance * len(prop_dict)),
                                        parent_point=(0.5, prop_start_y + line * prop_line_distance), point=(0.5, 0),
                                        color=(0, 0, 0, 80), fillet=base_fillet)
    prop_base_pos_on_parent = canvas.get_parent_box("part_2.prop_base")
    for prop_name, prop_data in prop_dict.items():
        """prop_name: 属性键名 prop_data: 原始数据"""

        if alpha == 80:
            alpha = 0
        else:
            alpha = 80
        """属性条底图，间隔深色"""
        prop_base = canvas.part_2.prop_base.__dict__["prop_base_%s" % line] = Rectangle(uv_size=(1, 1), box_size=(1, len(prop_dict) ** -1),
                                                                                        parent_point=(0, line * len(prop_dict) ** -1), point=(0, 0),
                                                                                        color=(0, 0, 0, alpha), fillet=base_fillet, keep_ratio=False)
        """属性材质图标"""
        prop_base.prop_icon = Img(uv_size=(1, 1), box_size=(0.5, 0.5), parent_point=(0.05, 0.5), point=(0.5, 0.5),
                                  img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % prop_name)))
        """属性可读名称"""
        prop_base.prop_show_name = Text(uv_size=(1, 1), box_size=(0.8, 0.55), parent_point=(0.1, 0.5), point=(0, 0.5), font=font_hywh, dp=1, force_size=True,
                                        text=loc_data.get(lang, loc_data["en"]).get(prop_name, prop_name))
        if prop_data["type"] == "int1":
            prop_base.value = Text(uv_size=(1, 1), box_size=(0.6, 0.45), parent_point=(0.98, 0.32), point=(1, 0.5), font=font_hywh, force_size=True, dp=1,
                                   text=str(int(prop_data["value"])))
            prop_base.add = Text(uv_size=(1, 1), box_size=(0.6, 0.33), parent_point=(0.98, 0.72), point=(1, 0.5), font=font_hywh, force_size=True, dp=1,
                                 text="+" + str(int(prop_data["add"])), color=Color.hex2dec("FF05C05F"))
            add_pos = canvas.get_parent_box("part_2.prop_base.prop_base_%s.add" % line)
            prop_base.base = Text(uv_size=(1, 1), box_size=(0.6, 0.33), parent_point=(add_pos[0], 0.72), point=(1, 0.5), font=font_hywh, force_size=True, dp=1,
                                  text=str(int(prop_data["base"])))
        elif prop_data["type"] == "int2":
            prop_base.value = Text(uv_size=(1, 1), box_size=(0.4, 0.5),
                                   parent_point=(0.98, 0.5), point=(1, 0.5), text=str(int(prop_data["value"])), font=font_hywh, force_size=True)
        elif prop_data["type"] == "percent":
            prop_base.value = Text(uv_size=(1, 1), box_size=(0.4, 0.5),
                                   parent_point=(0.98, 0.5), point=(1, 0.5), text=str(round(prop_data["value"] * 100, prop_data.get("accuracy", 1))) + "%", font=font_hywh,
                                   force_size=True)
        line += 1

    """圣遗物部分"""
    y0 = 0.04
    artifact_distance = 0.15
    [x0, y0, 0, 0]
    0
    for artifact_i, artifact in enumerate(artifacts):
        artifact: Equip
        detect_enka_texture(artifact.flat.icon)
        """圣遗物底图"""
        artifact_bg = Rectangle(uv_size=(1, 1), box_size=(0.9, 0.1428), parent_point=(0.5, y0 + artifact_distance * artifact_i), point=(0.5, 0), fillet=base_fillet,
                                color=(0, 0, 0, 80), keep_ratio=False)
        canvas.part_3.__dict__[f"artifact_{artifact_i}"] = artifact_bg
        """圣遗物贴图"""
        artifact_bg.icon = Img(uv_size=(1, 1), box_size=(0.5, 1), parent_point=(0, 0), point=(0, 0),
                               img=Image.open(os.path.join(Path.cache, f'genshin/{artifact.flat.icon}.png')))
        """圣遗物类型贴图"""
        artifact_bg.icon.type = Img(
            uv_size=(1, 1), box_size=(0.3, 0.3), parent_point=(0.03, 0.03), point=(0, 0),
            img=Image.open(os.path.join(Path.res, f'textures/genshin/{artifact.flat.equipType}.png'))
        )
        artifact_texture_pos = canvas.get_parent_box(f"part_3.artifact_{artifact_i}.icon")
        """圣遗物星级图"""
        artifact_bg.star = Img(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=((artifact_texture_pos[0] + artifact_texture_pos[2]) / 2, artifact_texture_pos[3] - 0.09),
                               point=(0.5, 1), img=Image.open(os.path.join(Path.res, "textures", "genshin", f'star_{artifact.flat.rankLevel}.png')))
        main_attr = artifact.flat.reliquaryMainstat.mainPropId
        main_attr_value = artifact.flat.reliquaryMainstat.statValue
        if main_attr in percent_prop:
            value = str(main_attr_value) + "%"
        else:
            value = str(main_attr_value)

        artifact_bg.main_attr = Img(uv_size=(1, 1), box_size=(0.5, 0.25),
                                    parent_point=(0.25, 0.185), point=(0, 0),
                                    img=Image.open(os.path.join(Path.res, "textures", "genshin", f"{main_attr}.png")))
        artifact_bg.main_attr_value = Text(uv_size=(1, 1), box_size=(0.5, 0.2),
                                           parent_point=(0.25, 0.65), point=(0, 0), text=value, font=font_hywh, force_size=True)
        canvas.draw_line(f"part_3.artifact_{artifact_i}", p1=(0.465, 0.12), p2=(0.465, 0.88), color=(80, 80, 80, 255), width=3)
        canvas.draw_line(f"part_3.artifact_{artifact_i}", p1=(0.48, 0.44), p2=(0.95, 0.44), color=(80, 80, 80, 255), width=3)
        canvas.draw_line(f"part_3.artifact_{artifact_i}", p1=(0.48, 0.9), p2=(0.95, 0.9), color=(80, 80, 80, 255), width=3)
        canvas.draw_line(f"part_3.artifact_{artifact_i}", p1=(0.45, 0.5), p2=(0.25, 0.5), color=(80, 80, 80, 255), width=3)
        artifact_bg.level = Text(uv_size=(1, 1), box_size=(0.5, 0.18), parent_point=(0.33, 0.17),
                                 point=(0, 0), text=" +" + str(artifact.reliquary.level - 1), font=font_hywh, force_size=True, fillet=5, fill=(255, 255, 255, 60),
                                 rectangle_side=2)
        x10 = 0.5
        y10 = 0.19
        dx = 0.25
        dy = 0.45
        for sub_i, sub_data in enumerate(artifact.flat.reliquarySubstats):
            x = x10 + sub_i % 2 * dx
            y = y10 + sub_i // 2 * dy
            sub_attr = sub_data.appendPropId
            sub_value = sub_data.statValue
            if sub_attr in percent_prop:
                value = str(sub_value) + "%"
            else:
                value = str(sub_value)
            artifact_bg.__dict__["sub_attr_icon_%s" % sub_i] = Img(
                uv_size=(1, 1), box_size=(0.5, 0.2),
                parent_point=(x, y), point=(0, 0),
                img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % sub_attr)))
            artifact_bg.__dict__["sub_attr_value_%s" % sub_i] = Text(
                uv_size=(1, 1), box_size=(0.5, 0.2),
                parent_point=(x + 0.07, y), point=(0, 0), text=value, font=font_hywh, force_size=True)

    """圣遗物套装效果 Part2"""
    artifact_set_words = []
    for sets in artifact_set_dict.items():
        sets = list(sets)
        if sets[0] in sacrificer:
            sets[1] = 1
            artifact_set_words.append(sets)
        elif sets[1] >= 4:
            sets[1] = 4
            artifact_set_words.append(sets)
        elif sets[1] >= 2:
            sets[1] = 2
            artifact_set_words.append(sets)

    set_word = canvas.part_2.artifact_set_info = Panel(
        uv_size=(1, 1), box_size=(1, 0.15), parent_point=(0.5, clamp(prop_base_pos_on_parent[3] + 0.01, 0.85, 1)), point=(0.5, 0)
    )
    for w_i, word in enumerate(artifact_set_words):
        set_word.__dict__["text_%s" % w_i] = Text(
            uv_size=(1, 1), box_size=(1, 0.25), parent_point=(0.5, 0.3 * w_i), point=(0.5, 0),
            text=f' {get_text_by_lang(word[0], lang, loc_data) + ": " + str(word[1])} ',
            font=font_hywh, color=Color.hex2dec("FF44ff00"), fillet=5, fill=(255, 255, 255, 60), rectangle_side=2)

    times = "%s-%s-%s %s:%s:%s" % tuple(playerData.update_time)
    canvas.player_info = Text(uv_size=(1, 1), box_size=(0.5, 0.01),
                              parent_point=(0.99, 0.99),
                              point=(1, 1), text="%s  %s  %s  UID： %s" % (times, lang, playerData.playerInfo.nickname, playerData.uid), font=font_hywh,
                              force_size=True)
    canvas.liteyuki_sign = Text(uv_size=(1, 1), box_size=(0.5, 0.01),
                                parent_point=(0.01, 0.99),
                                point=(0, 1), text=generate_signature, font=font_hywh, force_size=True)
    return canvas
