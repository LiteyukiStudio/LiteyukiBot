import aiohttp
from extraApi.base import ExtraData, Command


async def getQWCityInfo(params) -> list:
    """
    :return: 城市列表json
    """
    apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
    url = "https://geoapi.qweather.com/v2/city/lookup?"
    if "key" not in params:
        params["key"] = apiKey
    print(params["key"])

    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:
        return await r.json()


async def getQWRealTimeWeather(city: dict, params) -> dict:
    """
    :param city: 通过getHWCityInfo获取的元素
    :param params: 用户命令中的参数
    :return: 实时天气数据json
    """
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
    if params["key"] is None:
        params["key"] = apiKey
    if days <= 3:
        url = "https://api.qweather.com/v7/weather/%sd?" % 3
    else:
        url = "https://api.qweather.com/v7/weather/%sd?" % 30

    if "adm" in params:
        del params["adm"]
    if params.get("key", None) is None:
        params["key"] = apiKey
    params["location"] = city["id"]

    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:

        return await r.json()


async def getQWHoursWeather(city: dict, hours: int, params) -> dict:
    apiKey = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.weather.key", default=str())
    if params["key"] is None:
        params["key"] = apiKey
    if hours <= 24:
        url = "https://api.qweather.com/v7/weather/24h?"
    else:
        url = "https://api.qweather.com/v7/weather/%168h?"

    if "adm" in params:
        del params["adm"]
    if params.get("key", None) is None:
        params["key"] = apiKey
    params["location"] = city["id"]
    print(params)

    async with aiohttp.request("GET", url=url, params=params, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36',
    }) as r:

        return await r.json()
