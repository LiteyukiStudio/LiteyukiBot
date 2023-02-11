# 和风天气接口
from typing import Type

import jieba
from nonebot.internal.matcher import Matcher

from .model import *
from ...liteyuki_api.utils import *
from ...liteyuki_api.data import Data


def jieba_cut(word: str) -> list:
    """
    异步结巴分词，避免占用

    :param word:
    :return:
    """
    return jieba.lcut(word)


async def key_check(matcher: Type[Matcher]):
    if await Data(Data.globals, "qweather").get("key") is None:
        await matcher.finish("未配置key，轻雪天气部分查询服务无法运行！")


async def city_lookup(keyword: str, **kwargs) -> CityLookup | None:
    """
    建议异步执行
    查询不到结果时返回None

    :param keyword:
    :param kwargs:
    :return:
    """
    key, key_type = await Data(Data.globals, "qweather").get_many({"key": None, "key_type": None})
    url = "https://geoapi.qweather.com/v2/city/lookup?"
    params = {"key": key, "location": keyword}
    params.update(kwargs)
    resp = simple_request_get(url, params=params)
    if resp.json()["code"] == "200":
        return CityLookup(**resp.json())

    word_list = keyword.split()
    if len(word_list) >= 2:
        params["location"] = word_list[-1]
        params["adm"] = word_list[0]
        resp = simple_request_get(url, params=params)
        if resp.json()["code"] == "200":
            return CityLookup(**resp.json())

    word_list = jieba_cut(keyword)
    if len(word_list) >= 2:
        params["location"] = word_list[-1]
        params["adm"] = word_list[0]
        resp = simple_request_get(url, params=params)
        if resp.json()["code"] == "200":
            return CityLookup(**resp.json())
    return None


async def weather_now(location: str, lang="zh-hans", unit="m") -> WeatherNow:
    """
    建议异步执行
    :param location: id或坐标
    :param lang:
    :param unit:
    :return:
    """
    key, key_type = await Data(Data.globals, "qweather").get_many({"key": None, "key_type": None})
    url = f"https://{'dev' if key_type == 'dev' else ''}api.qweather.com/v7/weather/now?"
    resp = simple_request_get(url, params={"location": location, "lang": lang, "unit": unit, "key": key})
    if resp.json()["code"] == "200":
        return WeatherNow(**resp.json())

async def weather_daily(location: str, lang="zh-hans", unit="m", day=7) -> WeatherDaily:
    """

    :param day: (开发版仅支持3，7)3，7，10，15，30
    :param location: 坐标|城市id
    :param lang: 语言
    :param unit: 温度单位：i|m
    :return: 逐日天气
    """
    key, key_type = await Data(Data.globals, "qweather").get_many({"key": None, "key_type": None})
    url = f"https://{'dev' if key_type == 'dev' else ''}api.qweather.com/v7/weather/{day}d?"
    resp = simple_request_get(url, params={"location": location, "lang": lang, "unit": unit, "key": key})
    if resp.json()["code"] == "200":
        return WeatherDaily(**resp.json())

async def air_now(location: str, lang="zh-hans", unit="m") -> AirNow:
    key, key_type = await Data(Data.globals, "qweather").get_many({"key": None, "key_type": None})
    url = f"https://{'dev' if key_type == 'dev' else ''}api.qweather.com/v7/air/now?"
    resp = simple_request_get(url, params={"location": location, "lang": lang, "unit": unit, "key": key})
    if resp.json()["code"] == "200":
        return AirNow(**resp.json())

async def weather_hourly(location: str, lang="zh-hans", unit="m", hour=24) -> WeatherHourly:
    """
    :param location: 坐标|城市id
    :param lang: 语言
    :param unit: 温度单位：i|m
    :param hour: 小时数： (开发版仅支持24)24，72，168
    :return:
    """
    key, key_type = await Data(Data.globals, "qweather").get_many({"key": None, "key_type": None})
    url = f"https://{'dev' if key_type == 'dev' else ''}api.qweather.com/v7/weather/{hour}h?"
    resp = simple_request_get(url, params={"location": location, "lang": lang, "unit": unit, "key": key})
    if resp.json()["code"] == "200":
        return WeatherHourly(**resp.json())
