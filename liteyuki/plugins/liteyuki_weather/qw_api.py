from .qw_models import *
import httpx


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
        dev: bool = True,
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
        dev: bool = True,
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
        dev: bool = True,
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
        dev: bool = True
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
