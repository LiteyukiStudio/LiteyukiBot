import time

import aiohttp
from extraApi.base import ExtraData, Command


def match_custom_city(name, city_list: list):
    for city in city_list:
        if city["name"] in name or name in city["name"] or name == city["id"]:
            return city["name"]


async def getQWCityInfo(params) -> list:
    """
    :return: 城市列表json
    """

    apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
    url = "https://geoapi.qweather.com/v2/city/lookup?"
    if "key" not in params:
        params["key"] = apiKey

    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:
        if (await r.json())["code"] == "200":
            return await r.json()
        else:
            custom_pos = await ExtraData.get_global_data(key="kami.weather.custom_city_data", default=[])
            target_name = match_custom_city(params.get("location"), custom_pos)
            if target_name is None:
                return {"code": 404}
            for pos in custom_pos:
                if pos["name"] == target_name:
                    if params.get("lang", "zh") in ["zh"]:
                        return {"code": "200", "location": [pos]}
                    else:
                        pos["name"] = await Command.translate(pos["name"], from_lang="zh", to_lang=params.get("lang"))
                        pos["adm1"] = await Command.translate(pos["adm1"], from_lang="zh", to_lang=params.get("lang"))
                        pos["adm2"] = await Command.translate(pos["adm2"], from_lang="zh", to_lang=params.get("lang"))
                        pos["country"] = await Command.translate(pos["country"], from_lang="zh", to_lang=params.get("lang"))
                        return {"code": "200", "location": [pos]}


async def getQWRealTimeWeather(city: dict, params) -> dict:
    """
    :param city: 通过getHWCityInfo获取的元素
    :param params: 用户命令中的参数
    :return: 实时天气数据json
    """
    if city.get("custom"):
        weather = city.get("weatherData")
        datetime = list(time.localtime())
        weather["obsTime"] = "%s-%s-%sT%s:%s+00:00" % tuple(datetime[0:5])
        if "icon" not in weather:
            weather["icon"] = city.get("id")
        if params.get("lang", "zh") != "zh":
            weather["text"] = await Command.translate(text=weather.get("text"), from_lang="zh", to_lang=params.get("lang"))
            weather["windDir"] = {"东风": "E", "东南风": "NE", "南": "S", "西南风": "SW", "西风": "W", "西北风": "NW", "北风": "N", "东北风": "NE"}.get(weather["windDir"], await Command.translate(
                text=weather.get("windDir"), from_lang="zh", to_lang=params.get("lang")))
        if params.get("unit") == "i":
            weather["temp"] = round(float(weather.get("temp", 0.0)) * 1.8 + 32, 1)
            weather["feelsLike"] = round(float(weather.get("feelsLike", 0.0)) * 1.8 + 32, 1)
            weather["dew"] = round(float(weather.get("dew", 0.0)) * 1.8 + 32, 1)
        return {"code": "200", "now": weather}
    else:
        apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
        url = "https://api.qweather.com/v7/weather/now?"

        if "adm" in params:
            del params["adm"]
        if params.get("key", None) is None:
            params["key"] = apiKey
        if params.get("location", None) is None or not params.get("location", "None").isdigit():
            params["location"] = city["id"]
        async with aiohttp.request("GET", url=url, params=params, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
        }) as r:

            return await r.json()


async def getQWDaysWeather(city: dict, days: int, params) -> dict:
    apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
    if params.get("key") is None:
        params["key"] = apiKey
    if days <= 3:
        url = "https://api.qweather.com/v7/weather/3d?"
    elif days <= 7:
        url = "https://api.qweather.com/v7/weather/7d?"
    elif days <= 10:
        url = "https://api.qweather.com/v7/weather/10d?"
    elif days <= 15:
        url = "https://api.qweather.com/v7/weather/15d?"
    else:
        url = "https://api.qweather.com/v7/weather/30d?"

    if "adm" in params:
        del params["adm"]
    params["location"] = city["id"]

    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:

        return await r.json()


async def getQWHoursWeather(city: dict, hours: int, params) -> dict:
    apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
    if params.get("key") is None:
        params["key"] = apiKey
    if hours <= 24:
        url = "https://api.qweather.com/v7/weather/24h?"
    elif hours <= 72:
        url = "https://api.qweather.com/v7/weather/72h?"
    else:
        url = "https://api.qweather.com/v7/weather/168h?"

    if "adm" in params:
        del params["adm"]
    params["location"] = city["id"]
    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:

        return await r.json()
