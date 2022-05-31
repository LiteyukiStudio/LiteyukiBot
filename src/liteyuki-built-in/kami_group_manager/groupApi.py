import re
from decimal import *
from typing import Union


def chinese2digit(cn):
    """中文转数字

    :param cn: 中文字符串
    :return: 数字
    >>> chinese2digit('十一')
    11
    >>> chinese2digit('九万八千零七十六点五四三二一')
    Decimal('98076.54321')
    """
    try:
        r = float(cn)
        return r
    except BaseException:
        if cn.isdigit():
            return int(cn)
    CN_NUM = {
        '〇': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
        '零': 0, '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5, '陆': 6, '柒': 7, '捌': 8, '玖': 9,
        '貮': 2, '两': 2
    }
    CN_UNIT = {
        '十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000, '万': 10000, '萬': 10000,
        '亿': 100000000, '億': 100000000, '兆': 1000000000000
    }

    cn = cn.split('点')
    integer = list(cn[0])  # 整数部分
    decimal = list(cn[1]) if len(cn) == 2 else []  # 小数部分
    unit = 0  # 当前单位
    parse = []  # 解析数组
    while integer:
        x = integer.pop()
        if x in CN_UNIT:
            # 当前字符是单位
            unit = CN_UNIT.get(x)
            if unit == 10000:
                parse.append('w')  # 万位
                unit = 1
            elif unit == 100000000:
                parse.append('y')  # 亿位
                unit = 1
            elif unit == 1000000000000:  # 兆位
                parse.append('z')
                unit = 1
            continue
        else:
            # 当前字符是数字
            dig = CN_NUM.get(x)
            if unit:
                dig *= unit
                unit = 0
            parse.append(dig)

    if unit == 10:  # 处理10-19的数字
        parse.append(10)

    result = 0
    tmp = 0
    while parse:
        x = parse.pop()
        if x == 'w':
            tmp *= 10000
            result += tmp
            tmp = 0
        elif x == 'y':
            tmp *= 100000000
            result += tmp
            tmp = 0
        elif x == 'z':
            tmp *= 1000000000000
            result += tmp
            tmp = 0
        else:
            tmp += x
    result += tmp

    if decimal:
        unit = 0.1
        getcontext().prec = len(decimal)  # 小数精度
        result = Decimal(float(result))
        tmp = Decimal(0)
        for x in decimal:
            dig = CN_NUM.get(x)
            tmp += Decimal(str(dig)) * Decimal(str(unit))
            unit *= 0.1
        getcontext().prec = len(result.to_eng_string()) + len(decimal)  # 完整精度
        result += tmp
    return result


def get_duration(raw_input: str) -> Union[int, None]:
    """
    :param raw_input:
    :return: 内部数据，0-
    不会限制区间

    错误输入返回None
    """
    if raw_input.isdigit():
        return int(raw_input)
    elif re.search(r"[0-9]+\.[0-9]+", str(raw_input)) is not None:
        if re.search(r"[0-9]+\.[0-9]+", str(raw_input)).group(0) == str(raw_input):
            return int(raw_input.split(".")[0])
    elif raw_input in ["cancel", "取消"]:
        return 0
    raw_input = raw_input.replace("个", "").replace("個", "")
    time_units = {
        "ms": 0.001,
        "毫秒": 0.001,
        "μs": 0.000001,
        "微秒": 0.000001,
        "ps": 0.000000000001,
        "皮秒": 0.000000000001,
        "ns": 0.000000001,
        "纳秒": 0.000000001,
        "year": 31536000,
        "month": 2592000,
        "week": 604800,
        "day": 86400,
        "hour": 3600,
        "minute": 60,
        "second": 1,
        "天": 86400,
        "d": 86400,
        "日": 86400,
        "时": 3600,
        "小时": 3600,
        "h": 3600,
        "分钟": 60,
        "分": 60,
        "m": 60,
        "秒钟": 1,
        "秒": 1,
        "s": 1,

        "刻钟": 900,
        "年": 31536000,
        "月": 2592000,
        "周": 604800,
        "候": 432000,
        "世纪": 3153600000,
        "旬": 864000,
        "三体时": 3156,
        "游戏刻": 0.05,
        "gt": 0.05,
        "rt": 0.05
    }
    duration = 0
    been_added = False
    for time_unit in time_units:
        re_exp = r"[.点0-9〇一二三四五六七八九十百千万亿零壹贰叁肆伍陆柒捌玖两拾]+" + time_unit
        if re.search(re_exp, raw_input) is not None:
            been_added = True
            result = re.search(re_exp, raw_input).group(0)
            number = result.replace(time_unit, "")
            duration += chinese2digit(number) * time_units[time_unit]
            raw_input = raw_input.replace(result, "")
    if been_added:
        return duration
    else:
        return 0


def get_duration_text(sec: int) -> str:
    """
    :param sec: 秒数
    :return: 反馈信息
    """
    duration_str = ""
    d = sec // 86400
    sec %= 86400
    h = sec // 3600
    sec %= 3600
    m = sec // 60
    sec %= 60
    s = sec
    duration = {"天": d, "小时": h, "分钟": m, "秒": s}
    for duration_item in duration.items():
        if duration_item[1] != 0:
            duration_str += "%d%s" % (duration_item[1], duration_item[0])
    return duration_str
