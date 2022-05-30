import aiohttp
import jieba
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
        return await response.json()
