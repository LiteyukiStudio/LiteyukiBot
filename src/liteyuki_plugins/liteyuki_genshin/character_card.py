import json
import os
import time
import traceback

import aiohttp
from PIL import ImageEnhance
from nonebot import on_message
from nonebot.adapters.onebot.v11 import Message, MessageSegment
from nonebot.exception import IgnoredException
from nonebot.params import CommandArg
from nonebot.utils import run_sync

from .rule import *
from .utils import *
from ...liteyuki_api.canvas import *
from ...liteyuki_api.data import Data
from ...liteyuki_api.canvas import Color

character_card = on_message(rule=args_end_with("面板"))
character_data = on_message(rule=args_end_with("角色数据"))


@character_card.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    file_pool = {}
    for f in resource_pool.keys():
        if os.path.exists(os.path.join(Path.data, "genshin", f)):
            file_pool[f] = json.load(open(os.path.join(Path.data, "genshin", f), encoding="utf-8"))
        else:
            await character_card.finish(data_lost, at_sender=True)
    args, kwargs = Command.formatToCommand(event.raw_message)
    character_name_input = args[0].strip().replace("面板", "").replace("#", "")
    if character_name_input == "更新":
        raise IgnoredException
    _break = False
    lang = "zh-CN"
    hd = kwargs.get("hd", "false")
    hash_id = str()
    entry = str()

    """旅行者判定"""
    if character_name_input in ["荧", "空"]:
        character_name_input = "旅行者"

    """遍历loc.json从输入的角色名查询词条的hash_id"""
    for lang, lang_data in file_pool["loc.json"].items():
        for hash_id, entry in lang_data.items():
            if character_name_input == entry:
                _break = True
                break
        if _break:
            break
    else:
        """从别称数据中查找hash_id"""
        for hash_id, aliases_list in Data(Data.globals, "genshin_game_data").get_data(key="character_aliases", default={}).items():
            if character_name_input in aliases_list:
                break
        else:
            await character_card.finish("角色名不存在或资源未更新", at_sender=True)
    lang = kwargs.get("lang", Data(Data.users, event.user_id).get_data(key="genshin.lang", default=lang))
    character_hash_id = hash_id

    character_id = 0
    character = {}
    """遍历character.json，获取角色id"""
    for character_id, character in file_pool["characters_enka.json"].items():
        if int(hash_id) == character["NameTextMapHash"]:
            character_id = character_id
            break
    else:
        await character_card.finish("角色名不存在或资源未更新", at_sender=True)

    """uid判定"""
    uid = kwargs.get("uid", Data(Data.users, event.user_id).get_data(key="genshin.uid", default=None))
    if uid is None:
        await character_card.finish("命令参数中未包含uid且未绑定过uid", at_sender=True)
    else:
        uid = int(uid)

    """先在本地查找角色数据，没有再在线请求"""
    global_db = Data(Data.globals, "genshin_player_data")
    local_data = global_db.get_data(str(uid), None)
    if local_data is not None and int(character_id) in [avatar["avatarId"] for avatar in local_data.get("avatarInfoList", [])]:
        player_data = local_data
    else:
        async with aiohttp.request("GET", url="https://enka.microgg.cn/u/%s" % uid) as resp:
            player_data = await resp.json()
            player_data["time"] = list(time.localtime())[0:5]

    """uid真实性判定"""
    if "playerInfo" not in player_data:
        await character_card.finish("uid信息不存在", at_sender=True)
    """角色展示判定i"""
    if "avatarInfoList" not in player_data:
        await character_card.finish(
            MessageSegment.text("请在游戏中显示角色详情") + MessageSegment.image(file="file:///%s" % os.path.join(Path.res, "textures", "genshin", "open_details.png")),
            at_sender=True)
    """ 判断旅行者"""
    is_traveler = False
    if character_id in ["10000005", "10000007"]:
        is_traveler = True

    user_character = {}
    for user_character in player_data["avatarInfoList"]:
        if user_character["avatarId"] == int(character_id) or user_character["avatarId"] in [10000005, 10000007] and is_traveler:
            if is_traveler:
                await character_card.finish("暂不支持查询旅行者面板", at_sender=True)
            break
    else:
        await character_card.finish("你的展板中没有此角色,请展示后发送「原神数据」以更新面板", at_sender=True)

    """角色在资源中的数据"""
    enka_character_data = character
    """玩家角色面板数据，来自enka"""
    player_character_data = user_character
    """面板基础信息获取"""
    """生命值上限 攻击力 防御力 元素精通 暴击 暴伤 充能 [附加两条值大于0的属性]"""
    """英语元素转希腊语元素"""
    greece_element = elements.get(enka_character_data["Element"], "Unknown")
    """汉仪文黑字体路径"""
    hywh_font = os.path.join(Path.res, "fonts/hywh-85w.ttf")
    msg_id = (await character_card.send("面板正在生成，请稍等几秒...", at_sender=True))["message_id"]
    """数据赋值处理部分"""
    """============="""
    """============="""
    """武器dict"""
    weapon = {}
    """圣遗物list"""
    artifacts = []
    for equipment in player_character_data["equipList"]:
        equipment: dict
        if "weapon" in equipment:
            weapon = equipment
        elif "reliquary" in equipment:
            artifacts.append(equipment)
    artifact_set_dict = {}
    """一件套圣遗物列表"""
    sacrificer = [
        "212557731",
        "262428003",
        "287454963",
        "2060049099",
        "3999792907"
    ]
    for artifact in artifacts:
        if artifact["flat"]["setNameTextMapHash"] in artifact_set_dict:
            artifact_set_dict[artifact["flat"]["setNameTextMapHash"]] += 1
        else:
            artifact_set_dict[artifact["flat"]["setNameTextMapHash"]] = 1

    """角色基础属性 int1基础值和附加值 int2只有最终值 percent百分比 | accuracy小数位默认0"""
    fight_prop = player_character_data["fightPropMap"]
    """百分比属性列表"""
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
        40: "FIGHT_PROP_FIRE_ADD_HURT",
        41: "FIGHT_PROP_ELEC_ADD_HURT",
        42: "FIGHT_PROP_WATER_ADD_HURT",
        43: "FIGHT_PROP_GRASS_ADD_HURT",
        44: "FIGHT_PROP_WIND_ADD_HURT",
        45: "FIGHT_PROP_ROCK_ADD_HURT",
        46: "FIGHT_PROP_ICE_ADD_HURT",
        26: "FIGHT_PROP_HEAL_ADD",
    }
    times = 0
    for fight_prop_id, fight_prop_name in addition_props.items():

        if fight_prop[str(fight_prop_id)] > 0:
            times += 1
            prop_dict[fight_prop_name] = {
                "type": "percent",
                "accuracy": 1,
                "value": fight_prop[str(fight_prop_id)]
            }
        if times >= 3:
            break

    try:
        # 名称 等级 好感度
        rank_level = {
            0: 20,
            1: 40,
            2: 50,
            3: 60,
            4: 70,
            5: 80,
            6: 90
        }
        """立绘"""
        base_fillet = 5
        chinese_name = file_pool["loc.json"]["zh-CN"].get(character_hash_id)
        if os.path.exists(os.path.join(Path.res, "textures", "genshin", "%s.png" % chinese_name)):
            character_wish_img = Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % chinese_name))
            character_wish_img = await run_sync(wish_img_crop)(character_wish_img)
        else:
            character_wish_img = Image.new("RGBA", (300, 300), color=(255, 255, 255, 255))
        await run_sync(resource_detect)(enka_character_data["SideIconName"].split("_")[-1])
        """大画布 | 渲染部分"""
        canvas = Canvas(Image.open(os.path.join(Path.res, "textures", "genshin", "%s_bg.png" % greece_element)))
        canvas.base_img = canvas.base_img.resize((1960, 1000))
        if hd == "true":
            canvas.base_img = canvas.base_img.resize((3920, 2000))
        """分割"""
        canvas.part_1 = Panel(uv_size=(3, 1), box_size=(1, 1), parent_point=(0, 0), point=(0, 0))
        canvas.part_2 = Panel(uv_size=(3, 1), box_size=(1, 1), parent_point=(1 / 3, 0), point=(0, 0))
        canvas.part_3 = Panel(uv_size=(3, 1), box_size=(1, 1), parent_point=(2 / 3, 0), point=(0, 0))
        """Part-1"""
        """角色立绘，命座，天赋，名称，等级，好感度"""
        canvas.part_1.avatar_img = Img(uv_size=(1, 1), box_size=(2, 1.0), parent_point=(0.5, 0.55), point=(0.5, 0.5), img=character_wish_img)
        canvas.part_1.name = Text(uv_size=(1, 1), box_size=(0.66, 0.06), parent_point=(0.03061 * 3, 0.06),
                                  point=(0, 0), text=get_lang_word(str(character_hash_id), lang, file_pool["loc.json"]), font=hywh_font)
        name_pos = await run_sync(canvas.get_actual_box)("part_1.name")
        if character_name_input != entry:
            """别名"""
            canvas.part_1.other_name = Text(uv_size=(1, 1), box_size=(0.36, 0.04), parent_point=((name_pos[2] + 0.005) * 3, name_pos[3]),
                                            point=(0, 1), text="(%s)" % character_name_input, font=hywh_font, color=(180, 180, 180, 255), force_size=True)
        """等级基础值"""
        canvas.part_1.level = Text(uv_size=(1, 1), box_size=(0.9, 0.04), parent_point=(0.03061 * 3, 0.17), point=(0, 0),
                                   text=("%s %s/" % (get_lang_word("level", lang, file_pool["loc.json"]), player_character_data["propMap"]["4001"]["val"])),
                                   font=hywh_font, force_size=True)
        level_pos = await run_sync(canvas.get_actual_box)("part_1.level")
        """等级最大值"""
        canvas.part_1.level_max = Text(uv_size=(1, 1), box_size=(0.9, 0.04), parent_point=(level_pos[2] * 3, 0.17), point=(0, 0),
                                       text="%s" % rank_level[int(player_character_data["propMap"]["1002"].get("val", 0))],
                                       font=hywh_font, color=(180, 180, 180, 255), force_size=True)

        canvas.part_1.love_icon = Img(uv_size=(1, 1), box_size=(0.9, 0.05), parent_point=(0.0306 * 3, 0.24),
                                      point=(0, 0), img=Image.open(os.path.join(Path.res, "textures", "genshin", "love.png")))
        love_icon_pos = canvas.get_actual_box("part_1.love_icon")
        canvas.part_1.love_level = Text(uv_size=(1, 1), box_size=(0.9, 0.04), parent_point=(love_icon_pos[2] * 3 + 0.03, (love_icon_pos[1] + love_icon_pos[3]) / 2),
                                        point=(0, 0.6),
                                        text="%s" % player_character_data["fetterInfo"]["expLevel"],
                                        font=hywh_font)
        """元素图"""
        canvas.part_1.element_icon = Img(uv_size=(1, 1), box_size=(0.9, 0.08), parent_point=(0.2959 * 3, 0.16),
                                         point=(0.5, 0.5), img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % greece_element)))
        """命之座部分"""
        constellation_distance = 0.1
        x0 = 0.045 * 3
        y0 = 0.38
        base_size = 0.12
        texture_size = 0.064
        constellation_num = len(player_character_data.get("talentIdList", []))
        for i, constellation_texture_name in enumerate(enka_character_data["Consts"]):
            await run_sync(resource_detect)(constellation_texture_name)
            if i + 1 <= constellation_num:
                # 已解锁命之座,先放底图，再放材质图
                canvas.part_1.__dict__["base_%s" % i] = Img(uv_size=(1, 1), box_size=(0.3, base_size), parent_point=(x0, y0 + i * constellation_distance),
                                                            point=(0.5, 0.5),
                                                            img=Image.open(os.path.join(Path.res, "textures", "genshin", "constellation_%s_unlocked.png" % greece_element)))
                canvas.part_1.__dict__["const_%s" % i] = Img(uv_size=(1, 1), box_size=(0.3, texture_size), parent_point=(x0, y0 + i * constellation_distance),
                                                             point=(0.5, 0.5),
                                                             img=Image.open(os.path.join(Path.cache, "genshin", "%s.png" % constellation_texture_name)))
            else:
                # 先放材质图，再放底图遮盖，最后加锁
                texture_img = await run_sync(ImageEnhance.Brightness(Image.open(os.path.join(Path.cache, "genshin", "%s.png" % constellation_texture_name)).convert("RGBA")).enhance)(0.5)
                base_img = await run_sync(
                    ImageEnhance.Brightness(Image.open(os.path.join(Path.res, "textures", "genshin", "constellation_%s_locked.png" % greece_element)).convert("RGBA")).enhance)(0.75)
                canvas.part_1.__dict__["const_%s" % i] = Img(uv_size=(1, 1), box_size=(0.3, base_size), parent_point=(x0, y0 + i * constellation_distance),
                                                             point=(0.5, 0.5),
                                                             img=base_img)
                canvas.part_1.__dict__["base_%s" % i] = Img(uv_size=(1, 1), box_size=(0.3, texture_size), parent_point=(x0, y0 + i * constellation_distance),
                                                            point=(0.5, 0.5),
                                                            img=texture_img)
                canvas.part_1.__dict__["lock_%s" % i] = Img(uv_size=(1, 1), box_size=(0.3, 0.032), parent_point=(x0, y0 + i * constellation_distance),
                                                            point=(0.5, 0.5),
                                                            img=Image.open(os.path.join(Path.res, "textures", "genshin", "locked.png")))

        """P1天赋部分"""
        x0 = 0.2959 * 3
        y0 = 0.58
        skill_distance = 0.14
        """遍历三个天赋"""
        for skill_i, skill_data in enumerate(enka_character_data["Skills"].items()):
            skill_id = skill_data[0]
            skill_texture = skill_data[1]
            await run_sync(resource_detect)(skill_texture)
            skill_level = player_character_data["skillLevelMap"][skill_id]
            add = False
            if skill_i == 1 and constellation_num >= 3:
                skill_level += 3
                add = True
            if skill_i == 2 and constellation_num >= 5:
                skill_level += 3
                add = True
            """天赋底图"""
            canvas.part_1.__dict__["skill_base_%s" % skill_i] = Img(uv_size=(1, 1), box_size=(0.3, 0.12), parent_point=(x0, y0 + skill_i * skill_distance),
                                                                    point=(0.5, 0.5),
                                                                    img=Image.open(os.path.join(Path.res, "textures", "genshin", "talent.png")))
            """天赋图"""
            canvas.part_1.__dict__["talent_%s" % skill_i] = Img(uv_size=(1, 1), box_size=(0.1, 0.08), parent_point=(x0, y0 + skill_i * skill_distance),
                                                                point=(0.5, 0.5),
                                                                img=Image.open(os.path.join(Path.cache, "genshin", "%s.png" % skill_texture)))
            talent_base_pos = await run_sync(canvas.get_actual_box)("part_1.skill_base_%s" % skill_i)
            """天赋等级底图"""
            talent_base = canvas.part_1.__dict__["talent_level_base_%s" % skill_i] = \
                Img(uv_size=(1, 1), box_size=(0.1, 0.03), parent_point=((talent_base_pos[0] + talent_base_pos[2]) / 2 * 3, talent_base_pos[3]), point=(0.5, 1),
                    img=Image.open(os.path.join(Path.res, "textures/genshin/talent_level_base_%s.png" % ("add" if add else "normal"))))

            """命之座加成为蓝色等级数字"""
            if add and skill_level == 13 or not add and skill_level == 10:
                color = Color.hex2dec("FFFFEE00")
            else:
                color = (255, 255, 255, 255)
            """天赋等级"""
            talent_base.level = Text(uv_size=(1, 1), box_size=(1.5, 0.8),
                                     parent_point=(0.5, 0.5),
                                     point=(0.5, 0.5), text=str(skill_level), font=hywh_font, color=color, force_size=True)

        """武器部分"""
        # 武器图

        start_line_x = 0.016938 * 3
        end_line_x = 0.32306 * 3
        start_line_y = 0.4
        star = weapon["flat"]["rankLevel"]
        """武器贴图缓存检测"""
        await run_sync(resource_detect)(weapon["flat"]["icon"])
        """武器贴图"""
        canvas.part_2.weapon_icon = Img(uv_size=(1, 1), box_size=(0.54, 0.25), parent_point=(start_line_x, 0.05),
                                        point=(0, 0), img=Image.open(os.path.join(Path.cache, "genshin", "%s.png" % weapon["flat"]["icon"])))
        """武器贴图位置"""
        weapon_pos = await run_sync(canvas.get_actual_box)("part_2.weapon_icon")
        canvas.part_2.weapon_icon.weapon_bar = Img(
            uv_size=(1, 1), box_size=(1, 0.25), parent_point=(0.5, 1),
            point=(0.5, 0.5), img=Image.open(os.path.join(Path.res, "textures/genshin/weapon_bar_star_%s.png" % star))
        )
        """武器名"""
        canvas.weapon_name = Text(uv_size=(1, 1), box_size=(0.18, 0.05), parent_point=(weapon_pos[2] + 0.019, weapon_pos[1] + 0.03),
                                  point=(0, 0), text=get_lang_word(weapon["flat"]["nameTextMapHash"], lang, loc=file_pool["loc.json"]), font=hywh_font)

        """武器星级"""
        canvas.weapon_star = Img(uv_size=(1, 1), box_size=(0.25, 0.04), parent_point=((weapon_pos[0] + weapon_pos[2]) / 2, weapon_pos[3]),
                                 point=(0.5, 1), img=Image.open(os.path.join(Path.res, "textures/genshin/star_%s.png" % star)))

        """武器属性部分，武器属性底图"""
        canvas.part_2.weapon_info = Rectangle(uv_size=(1, 1), box_size=(0.4593, 0.155), parent_point=(0.4898, 0.155),
                                              point=(0, 0), color=(0, 0, 0, 80), fillet=base_fillet)

        stats_distance = 0.4
        x0 = 0.1
        y0 = 0.25
        y1 = 0.75
        for i, stats in enumerate(weapon["flat"]["weaponStats"]):
            canvas.part_2.weapon_info.__dict__["prop_icon_%s" % i] = Img(uv_size=(1, 1), box_size=(0.22, 0.21), parent_point=(x0 + i * stats_distance, y0),
                                                                         point=(0.5, 0.5),
                                                                         img=Image.open(os.path.join(Path.res, "textures/genshin/%s.png" % stats["appendPropId"])))
            icon_pos = await run_sync(canvas.get_parent_box)("part_2.weapon_info.prop_icon_%s" % i)
            if stats["appendPropId"] in percent_prop:
                value = str(stats["statValue"]) + "%"
            else:
                value = str(stats["statValue"])
            canvas.part_2.weapon_info.__dict__["prop_value_%s" % i] = Text(uv_size=(1, 1), box_size=(0.5, 0.21), parent_point=(icon_pos[2] + 0.03, y0),
                                                                           point=(0, 0.5), text=value, font=hywh_font, force_size=True)

        """武器等级"""
        canvas.part_2.weapon_info.level = Text(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=(x0 - 0.05, y1),
                                               point=(0, 0.5),
                                               text="%s %s/" % (get_lang_word("level", lang, file_pool["loc.json"]), weapon["weapon"]["level"],),
                                               font=hywh_font, force_size=True)
        weapon_level_pos = await run_sync(canvas.get_parent_box)("part_2.weapon_info.level")
        canvas.part_2.weapon_info.level_max = Text(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=(weapon_level_pos[2], weapon_level_pos[1]),
                                                   point=(0, 0),
                                                   text="%s" % rank_level[weapon["weapon"].get("promoteLevel", 0)],
                                                   font=hywh_font, force_size=True, color=(180, 180, 180, 255))
        refine = 0
        if "affixMap" in weapon["weapon"]:
            for v in weapon["weapon"]["affixMap"].values():
                refine = v
        else:
            refine = 0
        """精炼度"""
        canvas.part_2.weapon_info.refine = Text(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=(0.8, y1),
                                                point=(0, 0.5),
                                                text="R%s" % (refine + 1),
                                                font=hywh_font, force_size=True, color=Color.hex2dec("FFFFEE00" if refine == 4 else "FFFFFFFF"))
        line = 0
        prop_line_distance = 0.06
        prop_start_y = 0.35
        alpha = 80
        """角色详细属性部分"""
        """属性浅色底图"""
        canvas.part_2.prop_base = Rectangle(uv_size=(1, 1), box_size=(0.95, prop_line_distance * len(prop_dict)),
                                            parent_point=(0.5, prop_start_y + line * prop_line_distance), point=(0.5, 0),
                                            color=(0, 0, 0, 80), fillet=base_fillet)
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
            prop_base.prop_icon = Img(uv_size=(1, 1), box_size=(0.5, 0.5), parent_point=(0.02, 0.5), point=(0, 0.5),
                                      img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % prop_name)))
            """属性可读名称"""
            prop_base.prop_show_name = Text(uv_size=(1, 1), box_size=(0.8, 0.5), parent_point=(0.1, 0.5), point=(0, 0.5), font=hywh_font, dp=1, force_size=True,
                                            text=file_pool["loc.json"].get(lang, file_pool["loc.json"]["zh-CN"]).get(prop_name, prop_name))
            if prop_data["type"] == "int1":
                prop_base.value = Text(uv_size=(1, 1), box_size=(0.6, 0.4), parent_point=(0.98, 0.32), point=(1, 0.5), font=hywh_font, force_size=True, dp=1,
                                       text=str(int(prop_data["value"])))
                prop_base.add = Text(uv_size=(1, 1), box_size=(0.6, 0.33), parent_point=(0.98, 0.72), point=(1, 0.5), font=hywh_font, force_size=True, dp=1,
                                     text="+" + str(int(prop_data["add"])), color=Color.hex2dec("FF05C05F"))
                add_pos = await run_sync(canvas.get_parent_box)("part_2.prop_base.prop_base_%s.add" % line)
                prop_base.base = Text(uv_size=(1, 1), box_size=(0.6, 0.33), parent_point=(add_pos[0], 0.72), point=(1, 0.5), font=hywh_font, force_size=True, dp=1,
                                      text=str(int(prop_data["base"])))
            elif prop_data["type"] == "int2":
                prop_base.value = Text(uv_size=(1, 1), box_size=(0.4, 0.45),
                                       parent_point=(0.98, 0.5), point=(1, 0.5), text=str(int(prop_data["value"])), font=hywh_font, force_size=True)
            elif prop_data["type"] == "percent":
                prop_base.value = Text(uv_size=(1, 1), box_size=(0.4, 0.45),
                                       parent_point=(0.98, 0.5), point=(1, 0.5), text=str(round(prop_data["value"] * 100, prop_data.get("accuracy", 1))) + "%", font=hywh_font, force_size=True)
            line += 1

        """圣遗物部分"""
        y0 = 0.06
        artifact_distance = 0.15
        artifact_pos = [x0, y0, 0, 0]
        artifact_i = 0
        for artifact_i, artifact in enumerate(artifacts):
            await run_sync(resource_detect)(artifact["flat"]["icon"])
            """圣遗物底图"""
            artifact_bg = Rectangle(uv_size=(1, 1), box_size=(0.9, 0.1428), parent_point=(0.5, y0 + artifact_distance * artifact_i), point=(0.5, 0), fillet=base_fillet,
                                    color=(0, 0, 0, 80), keep_ratio=False)
            canvas.part_3.__dict__["artifact_%s" % artifact_i] = artifact_bg
            """圣遗物贴图"""
            artifact_bg.icon = Img(uv_size=(1, 1), box_size=(0.5, 1), parent_point=(0, 0), point=(0, 0),
                                   img=Image.open(os.path.join(Path.cache, "genshin", "%s.png" % artifact["flat"]["icon"])))
            artifact_texture_pos = canvas.get_parent_box("part_3.artifact_%s.icon" % artifact_i)
            """圣遗物星级图"""
            artifact_bg.star = Img(uv_size=(1, 1), box_size=(0.5, 0.2), parent_point=((artifact_texture_pos[0] + artifact_texture_pos[2]) / 2, artifact_texture_pos[3] - 0.09),
                                   point=(0.5, 1), img=Image.open(os.path.join(Path.res, "textures", "genshin", "star_%s.png" % artifact["flat"]["rankLevel"])))
            main_attr = artifact["flat"]["reliquaryMainstat"]["mainPropId"]
            main_attr_value = artifact["flat"]["reliquaryMainstat"]["statValue"]
            if main_attr in percent_prop:
                value = str(main_attr_value) + "%"
            else:
                value = str(main_attr_value)

            artifact_bg.main_attr = Img(uv_size=(1, 1), box_size=(0.5, 0.25),
                                        parent_point=(0.25, 0.185), point=(0, 0),
                                        img=Image.open(os.path.join(Path.res, "textures", "genshin", "%s.png" % main_attr)))
            artifact_bg.main_attr_value = Text(uv_size=(1, 1), box_size=(0.5, 0.2),
                                               parent_point=(0.25, 0.65), point=(0, 0), text=value, font=hywh_font, force_size=True)
            canvas.draw_line("part_3.artifact_%s" % artifact_i, p1=(0.465, 0.12), p2=(0.465, 0.88), color=(80, 80, 80, 255), width=3)
            canvas.draw_line("part_3.artifact_%s" % artifact_i, p1=(0.48, 0.44), p2=(0.95, 0.44), color=(80, 80, 80, 255), width=3)
            canvas.draw_line("part_3.artifact_%s" % artifact_i, p1=(0.48, 0.9), p2=(0.95, 0.9), color=(80, 80, 80, 255), width=3)
            canvas.draw_line("part_3.artifact_%s" % artifact_i, p1=(0.45, 0.5), p2=(0.25, 0.5), color=(80, 80, 80, 255), width=3)
            artifact_bg.level = Text(uv_size=(1, 1), box_size=(0.5, 0.18), parent_point=(0.33, 0.17),
                                     point=(0, 0), text="+" + str(artifact["reliquary"]["level"] - 1), font=hywh_font, force_size=True)
            x10 = 0.5
            y10 = 0.19
            dx = 0.25
            dy = 0.45
            for sub_i, sub_data in enumerate(artifact["flat"]["reliquarySubstats"]):
                x = x10 + sub_i % 2 * dx
                y = y10 + sub_i // 2 * dy
                sub_attr = sub_data["appendPropId"]
                sub_value = sub_data["statValue"]
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
                    parent_point=(x + 0.07, y), point=(0, 0), text=value, font=hywh_font, force_size=True)

        """圣遗物套装效果"""
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
        dy = 0.05
        set_word = Img(uv_size=(1, 1), box_size=(1, 0.1428), parent_point=(0.5, y0 + artifact_distance * (artifact_i + 1)), point=(0.5, 0),
                       img=Image.open(os.path.join(Path.res, "textures", "genshin", "artifact_bg.png")))
        canvas.part_3.set_word = set_word

        for w_i, word in enumerate(artifact_set_words):
            set_word.__dict__["text_%s" % w_i] = Text(
                uv_size=(1, 1), box_size=(0.5, 0.25), parent_point=(0.3, w_i * 0.26 + 0.1), point=(0, 0),
                text=get_lang_word(word[0], lang, file_pool["loc.json"]) + ": " + str(word[1]),
                font=hywh_font, color=Color.hex2dec("FF44ff00"))
        set_word.flower = Img(uv_size=(1, 1), box_size=(0.8, 0.8),
                              parent_point=(0.04, 0.5), point=(0, 0.5),
                              img=Image.open(os.path.join(Path.res, "textures", "genshin", "flower.png")))
        times = "%s-%s-%s %s:%s" % tuple(player_data.get("time", list(time.localtime())[0:5]))
        canvas.player_info = Text(uv_size=(1, 1), box_size=(0.5, 0.025),
                                  parent_point=(0.99, 0.99),
                                  point=(1, 1), text="%s    Language: %s    %s    UID： %s" % (times, lang, player_data["playerInfo"]["nickname"], uid), font=hywh_font,
                                  force_size=True)
        canvas.liteyuki_sign = Text(uv_size=(1, 1), box_size=(0.5, 0.025),
                                    parent_point=(0.01, 0.99),
                                    point=(0, 1), text=liteyuki_sign, font=hywh_font, force_size=True)

        await character_card.send(MessageSegment.image(file="file:///%s" % await run_sync(canvas.export_cache)()))
        await bot.delete_msg(message_id=msg_id)
        canvas.delete()

    except BaseException as e:
        await bot.delete_msg(message_id=msg_id)
        await character_card.finish("数据资源可能缺失或出现错误，请检查:%s\n请尝试发送「原神资源更新」以更新资源" % traceback.format_exception(e), at_sender=True)


@character_data.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    file_pool = {}
    for f in resource_pool.keys():
        if os.path.exists(os.path.join(Path.data, "genshin", f)):
            file_pool[f] = json.load(open(os.path.join(Path.data, "genshin", f), encoding="utf-8"))
        else:
            await character_card.finish(data_lost, at_sender=True)
    args, kwargs = Command.formatToCommand(event.raw_message)
    character_name_input = args[0].strip().replace("角色数据", "")
    _break = False
    lang = "zh-CN"
    hash_id = str()
    entry = str()

    """旅行者判定"""
    if character_name_input in ["荧", "空"]:
        character_name_input = "旅行者"

    """遍历loc.json从输入的角色名查询词条的hash_id"""
    for lang, lang_data in file_pool["loc.json"].items():
        for hash_id, entry in lang_data.items():
            if character_name_input == entry:
                _break = True
                break
        if _break:
            break
    else:
        """从别称数据中查找hash_id"""
        for hash_id, aliases_list in Data(Data.globals, "genshin_game_data").get_data(key="character_aliases", default={}).items():
            if character_name_input in aliases_list:
                break
        else:
            await character_card.finish("角色名不存在或资源未更新", at_sender=True)
    lang = kwargs.get("lang", Data(Data.users, event.user_id).get_data(key="genshin.lang", default=lang))
    character_hash_id = hash_id

    character_id = 0
    character = {}
    """遍历character.json，获取角色id"""
    for character_id, character in file_pool["characters_enka.json"].items():
        if int(hash_id) == character["NameTextMapHash"]:
            character_id = character_id
            break
    else:
        await character_card.finish("角色名不存在或资源未更新", at_sender=True)

    """uid判定"""
    uid = kwargs.get("uid", Data(Data.users, event.user_id).get_data(key="genshin.uid", default=None))
    if uid is None:
        await character_card.finish("命令参数中未包含uid且未绑定过uid", at_sender=True)
    else:
        uid = int(uid)

    """先在本地查找角色数据，没有再在线请求"""
    global_db = Data(Data.globals, "genshin_player_data")
    local_data = global_db.get_data(str(uid), None)
    if local_data is not None and int(character_id) in [avatar["avatarId"] for avatar in local_data.get("avatarInfoList", [])]:
        player_data = local_data
    else:
        async with aiohttp.request("GET", url="https://enka.network/u/%s/__data.json" % uid) as resp:
            player_data = await resp.json()
            player_data["time"] = list(time.localtime())[0:5]

    """uid真实性判定"""
    if "playerInfo" not in player_data:
        await character_card.finish("uid信息不存在", at_sender=True)
    """角色展示判定i"""
    if "avatarInfoList" not in player_data:
        await character_card.finish(
            MessageSegment.text("请在游戏中显示角色详情") + MessageSegment.image(file="file:///%s" % os.path.join(Path.res, "textures", "genshin", "open_details.png")),
            at_sender=True)
    """ 判断旅行者"""
    is_traveler = False
    if character_id in ["10000005", "10000007"]:
        is_traveler = True

    user_character = {}
    for user_character in player_data["avatarInfoList"]:
        if user_character["avatarId"] == int(character_id) or user_character["avatarId"] in [10000005, 10000007] and is_traveler:
            if is_traveler:
                await character_card.finish("暂不支持查询旅行者面板", at_sender=True)
            break
    else:
        await character_card.finish("你的展板中没有此角色,请展示后发送「原神数据」以更新面板", at_sender=True)

    """角色在资源中的数据"""
    enka_character_data = character
    """玩家角色面板数据，来自enka"""
    player_character_data = user_character
    name = file_pool["loc.json"].get(lang).get(hash_id)
    save_path = os.path.join(Path.cache, "uid%s_%s.json" % (uid, name))
    json.dump(fp=open(save_path, "w", encoding="utf-8"), obj=player_character_data, ensure_ascii=False, indent=4)
    if event.message_type == "private":
        await bot.call_api("upload_private_file", user_id=event.user_id, file="%s" % save_path, name="uid%s_%s.json" % (uid, name))
    else:
        await bot.call_api("upload_group_file", group_id=event.group_id, file="%s" % save_path, name="uid%s_%s.json" % (uid, name))
