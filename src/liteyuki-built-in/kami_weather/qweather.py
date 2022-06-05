import aiohttp
import jieba
from ...extraApi.base import ExtraData
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


class GeoApi:

    @staticmethod
    async def lookup_city(location: str, key: str, **kwargs) -> dict:
        """
        查询城市id

        支持配置自定义城市

        其他参数见: https://dev.qweather.com/docs/api/geo/city-lookup/

        :param key: 和风天气应用key
        :param location: 搜索词
        :return: {"code": "200"...}
        """
        url = "https://geoapi.qweather.com/v2/city/lookup?"
        params = dict()
        params["key"] = key
        # 1.直查
        params["location"] = location
        params.update(kwargs)
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            if (await response.json()).get("code", "000") == "200":
                return await response.json()

        # 空格分词查
        word_list = location.split()
        params = dict()
        params["key"] = key
        params["location"] = word_list[-1]
        params["adm"] = word_list[0]
        params.update(kwargs)
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            if (await response.json()).get("code", "000") == "200":
                return await response.json()

        # 结巴分词查

        word_list = await jieba_cut(location)
        params = dict()
        params["key"] = key
        params["location"] = word_list[-1]
        params["adm"] = word_list[0]
        params.update(kwargs)
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            if (await response.json()).get("code", "000") == "200":
                return await response.json()

        # 高德查格点
        url = "https://restapi.amap.com/v5/place/text?"
        params = {"keywords": location, "key": await ExtraData.get_global_data("kami.map.key", default="")}
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as gd_response:
            if (await gd_response.json()).get("info", "0") == "OK":
                if len((await gd_response.json()).get("pois", [])) > 0:
                    gd_poi = (await gd_response.json()).get("pois", [])[0]
                    city = {"code": "200",
                            "location": [{
                                "is_gaode": True,
                                "name": gd_poi.get("adname", ""),
                                "poi_name": gd_poi.get("name", ""),
                                "adm2": gd_poi.get("cityname", ""),
                                "adm1": gd_poi.get("pname", ""),
                                "country": "中国",
                                "id": gd_poi.get("adcode", ""),
                                "lon": gd_poi.get("location").split(",")[0],
                                "lat": gd_poi.get("location").split(",")[1]
                            }]}

                    return city

        custom_cities = await ExtraData.get_resource_data(key="kami.weather.custom_city_data", default=[])
        for city in custom_cities:
            if location in city.get("name"):
                return {"code": "200", "location": [city]}
        else:
            return await response.json()

    @staticmethod
    async def top_city(key: str, **kwargs) -> dict:
        """
        :param key:
        :param kwargs:
        :return:

        其他参数见: https://dev.qweather.com/docs/api/geo/top-city/
        """
        url = "https://geoapi.qweather.com/v2/city/top?"
        params = {"key": kwargs.get("key", key), "range": kwargs.get("range", "world"), "number": kwargs.get("number", "10"), "lang": kwargs.get("lang", "zh")}
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def lookup_poi(location: str, _type: str, key: str, **kwargs) -> dict:
        """
        :param location:
        :param _type: scenic CSTA TSTA
        :param key:
        :param kwargs:
        :return:
        """
        url = "https://geoapi.qweather.com/v2/poi/lookup?"
        params = {"location": kwargs.get("location", location), "type": kwargs.get("type", _type), "key": kwargs.get("key", key), "number": kwargs.get("number", "10"),
                  "lang": kwargs.get("lang", "zh")}
        if kwargs.get("city") is not None:
            params["city"] = kwargs.get("city")
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def range_poi(location: str, _type: str, key: str, **kwargs) -> dict:
        """

        :param location:
        :param _type:
        :param key:
        :param kwargs:
        :return:

        https://dev.qweather.com/docs/api/geo/poi-range/
        """
        url = "https://geoapi.qweather.com/v2/poi/range?"
        params = {"location": kwargs.get("location", location), "type": kwargs.get("type", _type), "key": kwargs.get("key", key),
                  "radius": kwargs.get("radius", "5"), "number": kwargs.get("number", "10"), "lang": kwargs.get("lang", "zh")}
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            return await response.json()


class CityWeatherApi:

    @staticmethod
    async def get_now_weather(location: str, key: str, key_type: str, **kwargs) -> dict:
        """
        :param key_type: dev or com
        :param location: search_cities获取的城市id或者经纬度
        :param key: 和风天气key
        :param kwargs: https://dev.qweather.com/docs/api/weather/weather-now/
        :return: {}

        实时天气
        """
        url = url = "https://%sapi.qweather.com/v7/weather/now?" % ("dev" if key_type == "dev" else "")
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
        async with aiohttp.request("GET", url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def get_daily_weather(location: str, key: str, days: int, key_type: str, **kwargs) -> dict:
        """
        :param key_type:
        :param days: 天数[1, 30]，开发版支持3,7 商业版支持3,7,10,15,30，返回区间最大数量
        :param location:
        :param key:
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

        url = "https://%sapi.qweather.com/v7/weather/%sd?" % ("dev" if key_type == "dev" else "", days)
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
        async with aiohttp.request("GET", url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def get_hourly_weather(location: str, key: str, hours: int, key_type: str, **kwargs) -> dict:
        """
        :param key_type:
        :param hours: 1-168，但返回的是区间最大数量
        :param location:
        :param key:
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

        url = "https://%sapi.qweather.com/v7/weather/%sh?" % ("dev" if key_type == "dev" else "", hours)
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
        async with aiohttp.request("GET", url, params=params, headers=headers) as response:
            return await response.json()


class PointWeatherApi:
    # 格点天气API

    @staticmethod
    async def minutely_precip(location: str, key: str, **kwargs) -> dict:
        """
        :param location: 经纬度
        :param key:
        :param kwargs:
        :return:

        https://dev.qweather.com/docs/api/grid-weather/minutely/
        """
        url = "https://api.qweather.com/v7/minutely/5m?"
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh")}
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def get_now_weather(location: str, key: str, **kwargs) -> dict:
        """
        :param location: 经纬度
        :param key:
        :param kwargs:
        :return:

        https://dev.qweather.com/docs/api/grid-weather/minutely/
        """
        url = "https://api.qweather.com/v7/grid-weather/now?"
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh")}
        async with aiohttp.request("GET", url=url, params=params, headers=headers) as response:
            return await response.json()

    @staticmethod
    async def get_hourly_weather(location: str, key: str, hours: int, **kwargs) -> dict:
        """
        :param hours: 1-168，但返回的是区间最大数量
        :param location:
        :param key:
        :param kwargs:
        :return:

        逐小时天气
        """
        hours_list = [24, 72]
        for i in hours_list:
            if hours <= i:
                hours = i
                break
        else:
            hours = hours_list[-1]

        url = "https://api.qweather.com/v7/grid-weather/%sh?" % hours
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), "lang": kwargs.get("lang", "zh"), "unit": kwargs.get("unit", "m")}
        async with aiohttp.request("GET", url, params=params, headers=headers) as response:
            return await response.json()


class AirApi:
    # 空气Api
    @staticmethod
    async def now_air(location: str, key: str, dev: bool, lang: str = "zh", **kwargs):
        """
        :param dev: 是否为开发版
        :param location:
        :param key:
        :param lang:
        :return:

        https://dev.qweather.com/docs/api/air/air-now/

        实时空气质量
        """
        url = "https://%sapi.qweather.com/v7/air/now?"
        params = {"location": kwargs.get("location", location), "key": kwargs.get("key", key), }
