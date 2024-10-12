import aiohttp

from .qw_models import *
import httpx

from src.utils.base.data_manager import get_memory_data
from src.utils.base.language import Language

dev_url = "https://devapi.qweather.com/"  # 开发HBa
com_url = "https://api.qweather.com/"  # 正式环境


def get_qw_lang(lang: str) -> str:
    if lang in ["zh-HK", "zh-TW"]:
        return "zh-hant"
    elif lang.startswith("zh"):
        return "zh"
    elif lang.startswith("en"):
        return "en"
    else:
        return lang


async def check_key_dev(key: str) -> bool:
    url = "https://api.qweather.com/v7/weather/now?"
    params = {
        "location": "101010100",
        "key"     : key,
    }
    async with aiohttp.ClientSession() as client:
        resp = await client.get(url, params=params)
        return (await resp.json()).get("code") != "200"  # 查询不到付费数据为开发版


def get_local_data(ulang_code: str) -> dict:
    """
    获取本地化数据
    Args:
        ulang_code:

    Returns:

    """
    ulang = Language(ulang_code)
    return {
        "monday"            : ulang.get("weather.monday"),
        "tuesday"  : ulang.get("weather.tuesday"),
        "wednesday"         : ulang.get("weather.wednesday"),
        "thursday"          : ulang.get("weather.thursday"),
        "friday"            : ulang.get("weather.friday"),
        "saturday"          : ulang.get("weather.saturday"),
        "sunday"            : ulang.get("weather.sunday"),
        "today"             : ulang.get("weather.today"),
        "tomorrow"          : ulang.get("weather.tomorrow"),
        "day"               : ulang.get("weather.day"),
        "night"             : ulang.get("weather.night"),
        "no_aqi"            : ulang.get("weather.no_aqi"),
        "now-windVelocity"  : ulang.get("weather.now-windVelocity"),
        "now-humidity"      : ulang.get("weather.now-humidity"),
        "now-feelsLike"     : ulang.get("weather.now-feelsLike"),
        "now-precip"        : ulang.get("weather.now-precip"),
        "now-pressure"      : ulang.get("weather.now-pressure"),
        "now-vis"           : ulang.get("weather.now-vis"),
        "now-cloud"         : ulang.get("weather.now-cloud"),
        "astronomy-sunrise" : ulang.get("weather.astronomy-sunrise"),
        "astronomy-sunset"  : ulang.get("weather.astronomy-sunset"),
    }


async def city_lookup(
        location: str,
        key: str,
        adm: str = "",
        number: int = 20,
        lang: str = "zh",
) -> CityLookup:
    """
    通过关键字搜索城市信息
    Args:
        location:
        key:
        adm:
        number:
        lang: 可传入标准i18n语言代码，如zh-CN、en-US等

    Returns:

    """
    url = "https://geoapi.qweather.com/v2/city/lookup?"
    params = {
        "location": location,
        "adm"     : adm,
        "number"  : number,
        "key"     : key,
        "lang"    : lang,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return CityLookup.parse_obj(resp.json())


async def get_weather_now(
        key: str,
        location: str,
        lang: str = "zh",
        unit: str = "m",
        dev: bool = get_memory_data("is_dev", True),
) -> dict:
    url_path = "v7/weather/now?"
    url = dev_url + url_path if dev else com_url + url_path
    params = {
        "location": location,
        "key"     : key,
        "lang"    : lang,
        "unit"    : unit,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return resp.json()


async def get_weather_daily(
        key: str,
        location: str,
        lang: str = "zh",
        unit: str = "m",
        dev: bool = get_memory_data("is_dev", True),
) -> dict:
    url_path = "v7/weather/%dd?" % (7 if dev else 30)
    url = dev_url + url_path if dev else com_url + url_path
    params = {
        "location": location,
        "key"     : key,
        "lang"    : lang,
        "unit"    : unit,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return resp.json()


async def get_weather_hourly(
        key: str,
        location: str,
        lang: str = "zh",
        unit: str = "m",
        dev: bool = get_memory_data("is_dev", True),
) -> dict:
    url_path = "v7/weather/%dh?" % (24 if dev else 168)
    url = dev_url + url_path if dev else com_url + url_path
    params = {
        "location": location,
        "key"     : key,
        "lang"    : lang,
        "unit"    : unit,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return resp.json()


async def get_airquality(
        key: str,
        location: str,
        lang: str,
        pollutant: bool = False,
        station: bool = False,
        dev: bool = get_memory_data("is_dev", True),
) -> dict:
    url_path = f"airquality/v1/now/{location}?"
    url = dev_url + url_path if dev else com_url + url_path
    params = {
        "key"      : key,
        "lang"     : lang,
        "pollutant": pollutant,
        "station"  : station,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return resp.json()

async def get_astronomy(
        key: str,
        location: str,
        date: str,
        dev: bool = get_memory_data("is_dev", True),
) -> dict:
    url_path = f"v7/astronomy/sun?"
    url = dev_url + url_path if dev else com_url + url_path
    params = {
        "key"      : key,
        "location" : location,
        "date"     : date,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        return resp.json()