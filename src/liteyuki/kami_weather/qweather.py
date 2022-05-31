import aiohttp
import jieba
from ..extraApi.base import ExtraData
from nonebot.utils import run_sync

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
}


@run_sync
def jieba_cut(word: str) -> list:
    """
    异步结巴分词，避免占用

    :param word:
    :return:
    """
    return jieba.lcut(word)


async def search_cities(word: str, key: str, **kwargs) -> dict:
    """
    查询城市id

    支持配置自定义城市

    其他参数见: https://dev.qweather.com/docs/api/geo/city-lookup/

    :param key: 和风天气应用key
    :param word: 搜索词
    :return: {"code": "200"...}
    """
    url = "https://geoapi.qweather.com/v2/city/lookup?"
    params = dict()
    params["key"] = key
    # 1.直查
    params["location"] = word
    params.update(kwargs)
    async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
        if (await response.json()).get("code", "000") == "200":
            return await response.json()

    # 空格分词查
    word_list = word.split()
    params = dict()
    params["key"] = key
    params["location"] = word_list[-1]
    params["adm"] = word_list[0]
    params.update(kwargs)
    async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
        if (await response.json()).get("code", "000") == "200":
            return await response.json()

    # 结巴分词查

    word_list = await jieba_cut(word)
    params = dict()
    params["key"] = key
    params["location"] = word_list[-1]
    params["adm"] = word_list[0]
    params.update(kwargs)
    async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
        if (await response.json()).get("code", "000") == "200":
            return await response.json()

    custom_cities = await ExtraData.get_resource_data(key="kami.weather.custom_city_data", default=[])
    for city in custom_cities:
        if word in city.get("name"):
            return {"code": "200", "location": [city]}
    else:
        return await response.json()


async def get_now_weather(location: str, key: str, dev: True, **kwargs) -> dict:
    """
    :param location: search_cities获取的城市id或者经纬度
    :param key: 和风天气key
    :param dev: 是否为开发版
    :param kwargs: https://dev.qweather.com/docs/api/weather/weather-now/
    :return: {}

    实时天气
    """
    url = url = "https://%sapi.qweather.com/v7/weather/now?" % ("dev" if dev else "")
    params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
    async with aiohttp.request("GET", url, params=params, headers=headers) as response:
        return await response.json()


async def get_daily_weather(location: str, key: str, days: int, dev: True, **kwargs) -> dict:
    """
    :param days: 天数[1, 30]，开发版支持3,7 商业版支持3,7,10,15,30，返回区间最大数量
    :param location:
    :param key:
    :param dev:
    :param kwargs: https://dev.qweather.com/docs/api/weather/weather-daily-forecast/
    :return:

    逐天天气
    """
    days_list = [3, 7, 10, 15, 30]
    for i in days_list:
        if days <= i:
            days = i
            break
    else:
        days = days_list[-1]

    url = "https://%sapi.qweather.com/v7/weather/%sd?" % ("dev" if dev else "", days)
    params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
    async with aiohttp.request("GET", url, params=params, headers=headers) as response:
        return await response.json()


async def get_hourly_weather(location: str, key: str, hours: int, dev: True, **kwargs) -> dict:
    """
    :param hours: 1-168，但返回的是区间最大数量
    :param location:
    :param key:
    :param dev:
    :param kwargs:
    :return:

    逐小时天气
    """
    hours_list = [24, 72, 168]
    for i in hours_list:
        if hours <= i:
            hours = i
            break
    else:
        hours = hours_list[-1]

    url = "https://%sapi.qweather.com/v7/weather/%sh?" % ("dev" if dev else "", hours)
    params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
    async with aiohttp.request("GET", url, params=params, headers=headers) as response:
        return await response.json()
