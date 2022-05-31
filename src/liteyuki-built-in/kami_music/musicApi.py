import aiohttp
import json
from nonebot.adapters.onebot.v11 import MessageSegment, Message


async def getMusic(kw: str, plat: str):
    platform = {
        "163": {
            "name": "网易云音乐",
            "method": "POST",
            "url": "https://music.163.com/api/cloudsearch/pc",
            "params": {"s": kw, "type": 1, "offset": 0, "limit": 1}
        },
        "qq": {
            "name": "QQ音乐",
            "method": "GET",
            "url": "https://c.y.qq.com/soso/fcgi-bin/client_search_cp",
            "params": {"w": kw, "p": 1, "n": 1, "format": "json"}
        },
        "233": {
            "name": "bilibili音频区",
            "method": "GET",
            "url": "https://api.bilibili.com/audio/music-service-c/s",
            "params": {"keyword": kw, "page": 1, "pagesize": 1, "search_type": "music"}
        },
        "kg": {
            "name": "酷狗音乐",
            "method": "GET",
            "url": "http://mobilecdn.kugou.com/api/v3/search/song",
            "params": {
                "format": "json",
                "keyword": kw,
                "showtype": 1,
                "page": 1,
                "pagesize": 1,
            }
        }
    }
    platData = platform.get(plat, platform["163"])
    if plat not in platform:
        plat = "163"

    async with aiohttp.request(method=platData["method"], url=platData["url"], params=platData["params"]) as resp:
        resData = json.loads(await resp.text())
        if plat == "163":
            if songs := resData["result"]["songs"]:
                return MessageSegment.music("163", songs[0]["id"])
            else:
                return "在%s中什么都没有搜到呢" % platform[plat]["name"]
        elif plat == "qq":
            if songs := resData["data"]["song"]["list"]:
                return MessageSegment.music("qq", songs[0]["songid"])
            else:
                return "在%s中什么都没有搜到呢" % platform[plat]["name"]
        elif plat == "233":
            if songs := resData["data"]["result"]:
                info = songs[0]
                return MessageSegment.music_custom(
                    url=f"https://www.bilibili.com/audio/au{info['id']}",
                    audio=info["play_url_list"][0]["url"],
                    title=info["title"],
                    content=info["author"],
                    img_url=info["cover"],
                )
            else:
                return "在%s中什么都没有搜到呢" % platform[plat]["name"]
        elif plat == "kg":
            if songs := resData["data"]["info"]:
                hash_ = songs[0]["hash"]
                album_id = songs[0]["album_id"]
                song_url = "http://m.kugou.com/app/i/getSongInfo.php"
                params = {"cmd": "playInfo", "hash": hash_}
                async with aiohttp.request(method="GET", url=song_url, params=params) as respSong:

                    if info := json.loads(await respSong.text()):
                        return {
                            "type": "music",
                            "data": {
                                "type": "custom",
                                "url": f"https://www.kugou.com/song/#hash={hash_}&album_id={album_id}",
                                "audio": info["url"],
                                "title": info["songName"],
                                "content": info["author_name"],
                                "image": str(info["imgUrl"]).format(size=240),
                            }
                        }
            else:
                return "在%s中什么都没有搜到呢" % platform[plat]["name"]
        else:
            return "平台参数出错：%s" % platform[plat]["name"]
