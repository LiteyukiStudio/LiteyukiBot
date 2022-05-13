import httpx
from dataclasses import dataclass
from typing import Union, Tuple, Protocol
from nonebot.adapters.onebot.v11 import MessageSegment


async def search_qq(keyword: str) -> Union[str, MessageSegment]:
    url = "https://c.y.qq.com/soso/fcgi-bin/client_search_cp"
    params = {"p": 1, "n": 1, "w": keyword, "format": "json"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        result = resp.json()
    if songs := result["data"]["song"]["list"]:
        return MessageSegment.music("qq", songs[0]["songid"])
    return "QQ音乐中找不到相关的歌曲"


async def search_163(keyword: str) -> Union[str, MessageSegment]:
    url = "https://music.163.com/api/cloudsearch/pc"
    params = {"s": keyword, "type": 1, "offset": 0, "limit": 1}
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, params=params)
        result = resp.json()
    if songs := result["result"]["songs"]:
        return MessageSegment.music("163", songs[0]["id"])
    return "网易云音乐中找不到相关的歌曲"


async def search_kuwo(keyword: str) -> Union[str, MessageSegment]:
    search_url = "https://search.kuwo.cn/r.s"
    params = {
        "all": keyword,
        "pn": 0,
        "rn": 1,
        "ft": "music",
        "rformat": "json",
        "encoding": "utf8",
        "pcjson": "1",
        "vipver": "MUSIC_9.1.1.2_BCS2",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(search_url, params=params)
        result = resp.json()

        if songs := result["abslist"]:
            rid = str(songs[0]["MUSICRID"]).strip("MUSIC_")
            song_url = "http://m.kuwo.cn/newh5/singles/songinfoandlrc"
            params = {"musicId": rid, "httpsStatus": 1}
            resp = httpx.get(song_url, params=params)
            result = resp.json()

            if info := result["data"]["songinfo"]:
                play_url = "https://kuwo.cn/api/v1/www/music/playUrl"
                params = {"mid": rid, "type": "music", "httpsStatus": 1}
                resp = httpx.get(play_url, params=params)
                result = resp.json()

                if data := result["data"]:
                    return MessageSegment.music_custom(
                        url=f"https://kuwo.cn/play_detail/{rid}",
                        audio=data["url"],
                        title=info["songName"],
                        content=info["artist"],
                        img_url=info["pic"],
                    )
    return "酷我音乐中找不到相关的歌曲"


async def search_kugou(keyword: str) -> Union[str, MessageSegment]:
    search_url = "http://mobilecdn.kugou.com/api/v3/search/song"
    params = {
        "format": "json",
        "keyword": keyword,
        "showtype": 1,
        "page": 1,
        "pagesize": 1,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.get(search_url, params=params)
        result = resp.json()

        if songs := result["data"]["info"]:
            hash = songs[0]["hash"]
            album_id = songs[0]["album_id"]
            song_url = "http://m.kugou.com/app/i/getSongInfo.php"
            params = {"cmd": "playInfo", "hash": hash}
            resp = await client.get(song_url, params=params)

            if info := resp.json():
                return MessageSegment.music_custom(
                    url=f"https://www.kugou.com/song/#hash={hash}&album_id={album_id}",
                    audio=info["url"],
                    title=info["songName"],
                    content=info["author_name"],
                    img_url=str(info["imgUrl"]).format(size=240),
                )
    return "酷狗音乐中找不到相关的歌曲"


async def search_migu(keyword: str) -> Union[str, MessageSegment]:
    url = "https://m.music.migu.cn/migu/remoting/scr_search_tag"
    params = {"rows": 1, "type": 2, "keyword": keyword, "pgc": 1}
    headers = {"Referer": "https://m.music.migu.cn"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, headers=headers)
        result = resp.json()
    if songs := dict(result).get("musics", []):
        info = songs[0]
        return MessageSegment.music_custom(
            url=f"https://music.migu.cn/v3/music/song/{info['copyrightId']}",
            audio=info["mp3"],
            title=info["title"],
            content=info["singerName"],
            img_url=info["cover"],
        )
    return "咪咕音乐中找不到相关的歌曲"


async def search_bili(keyword: str) -> Union[str, MessageSegment]:
    search_url = "https://api.bilibili.com/audio/music-service-c/s"
    params = {"page": 1, "pagesize": 1, "search_type": "music", "keyword": keyword}
    async with httpx.AsyncClient() as client:
        resp = await client.get(search_url, params=params)
        result = resp.json()
    if songs := result["data"]["result"]:
        info = songs[0]
        return MessageSegment.music_custom(
            url=f"https://www.bilibili.com/audio/au{info['id']}",
            audio=info["play_url_list"][0]["url"],
            title=info["title"],
            content=info["author"],
            img_url=info["cover"],
        )
    return "B站音频区中找不到相关的歌曲"


class Func(Protocol):
    async def __call__(self, keyword: str) -> Union[str, MessageSegment]:
        ...


@dataclass
class Source:
    keywords: Tuple[str, ...]
    func: Func


sources = [
    Source(("点歌", "qq点歌", "QQ点歌"), search_qq),
    Source(("163点歌", "网易点歌", "网易云点歌"), search_163),
    Source(("kuwo点歌", "酷我点歌"), search_kuwo),
    Source(("kugou点歌", "酷狗点歌"), search_kugou),
    Source(("migu点歌", "咪咕点歌"), search_migu),
    Source(("bili点歌", "bilibili点歌", "b站点歌", "B站点歌"), search_bili),
]
