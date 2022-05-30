
import requests
import aiohttp

from ..extraApi.base import Command, ExtraData


async def get_poi(keywords: str = None, params: dict = None) -> dict:
    """
    :param keywords: 查询关键词
    :param params: https://lbs.amap.com/api/webservice/guide/api/search/
    :return:

    poi列表
    """
    if params is None:
        params = {}
    if keywords is not None:
        params["keywords"] = keywords
    params["key"] = await ExtraData.getData(targetType=ExtraData.Group, targetId=0, key="kami.map.key", default="")
    async with aiohttp.request("GET", url="https://restapi.amap.com/v5/place/text?", params=params) as r:
        return await r.json()


async def get_path(way: str, params: dict) -> dict:
    """
    :param way: 交通方式标识
    :param params: https://lbs.amap.com/api/webservice/guide/api/newroute#t9
    :return:
    se
    """
    r = requests.get(url="https://restapi.amap.com/v5/direction/%s?" % way, params=params).json()
    if way == "driving":
        pass
    elif way == "walking":
        pass
    elif way == "bicycling":
        pass
    elif way == "electrobike":
        pass
    else:
        pass


async def get_poi_bing(keywords) -> dict:
    kws, params = Command.formatToString(*keywords)