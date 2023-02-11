from typing import Tuple

from nonebot.internal.rule import Rule

from ...liteyuki_api.utils import Command

weather_lang_names = ("天气", "weather", "天気", "날씨")


def get_day(day, lang="zh-hans"):
    lang_day = {
        "zh-hans": {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"},
        "en": {1: "Mon", 2: "Tue", 3: "Wed", 4: "Thur", 5: "Fri", 6: "Sat", 7: "Sun"},
        "ja": {1: "月曜日", 2: "火曜日", 3: "水曜日", 4: "木曜日", 5: "金曜日", 6: "土曜日", 7: "日曜日"}
    }
    return lang_day.get(lang,lang_day["en"]).get(day)


def format_location_show_name(level_list: list) -> str:
    """
    格式化可读地名，例如：["中国", "北京市", "北京", "北京"] -> "中国 北京市 北京"

    :param level_list: 行政区列表
    :return: 格式化后的名字
    """
    new_list = []
    for loc in level_list:
        if loc not in new_list:
            new_list.append(loc)
    return " ".join(new_list)


def format_location_show_name_2(level_list: list) -> Tuple[str, str]:
    """
    天气卡片专用版1

    :param level_list:
    :return:
    """
    new_list = level_list
    for loc in level_list:
        if loc not in new_list:
            new_list.append(loc)
    return " ".join(new_list[0:-1]), new_list[-1]


@Rule
async def WEATHER_NOW(bot, event, state):
    """
    当且仅当参数字符以 天气（及其他语言）结尾时可触发，逐天天气，逐小时天气不会触发
    :param bot:
    :param event:
    :param state:
    :return:
    """
    args, kwargs = Command.formatToCommand(str(event.message))
    args = " ".join(args)
    if args.endswith(("逐天天气", "小时天气")):
        return False
    else:
        return args.endswith(weather_lang_names)
