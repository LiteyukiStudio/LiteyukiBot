import json
import os.path
import shutil
from typing import Optional

import nonebot
from arclet.alconna import Arparma, MultiVar
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand
import pip

import aiohttp, aiofiles
from typing_extensions import Any

from src.utils.data import LiteModel
from src.utils.language import get_user_lang
from src.utils.message import button, send_markdown
from src.utils.resource import get_res
from src.utils.typing import T_Bot, T_MessageEvent

npm_alc = on_alconna(
    Alconna(
        "lnpm",
        Subcommand(
            "update",
            alias=["u"],
        ),
        Subcommand(
            "search",
            Args["keywords", MultiVar(str)]["page", int, 1],
            alias=["s"],
        ),
        Subcommand(
            "install",
            Args["plugin_name", str],
            alias=["i"],
        ),
        Subcommand(
            "remove",
            Args["plugin_name", str],
            alias=["rm"],
        ),
    ),
    permission=SUPERUSER
)


class PluginTag(LiteModel):
    label: str
    color: str = '#000000'


class StorePlugin(LiteModel):
    name: str
    desc: str
    module_name: str
    project_link: str = ''
    homepage: str = ''
    author: str = ''
    type: str | None = None
    version: str | None = ''
    time: str = ''
    tags: list[PluginTag] = []
    is_official: bool = False


@npm_alc.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
    ulang = get_user_lang(str(event.user_id))

    if not os.path.exists("data/liteyuki/plugins.json"):
        shutil.copy(get_res('unsorted/plugins.json'), "data/liteyuki/plugins.json")
        nonebot.logger.info("Please update plugin store data file.")

    if result.subcommands.get("update"):
        r = await npm_update()
        if r:
            await npm_alc.finish(ulang.get("npm.store_update_success"))
        else:
            await npm_alc.finish(ulang.get("npm.store_update_failed"))

    elif result.subcommands.get("search"):
        keywords: list[str] = result.subcommands["search"].args.get("keywords")
        rs = await npm_search(keywords)
        if len(rs):
            reply = f"{ulang.get('npm.search_result')} | {ulang.get('npm.total', TOTAL=len(rs))}\n***"
            for plugin in rs[:min(10, len(rs))]:
                reply += (f"\n{button(ulang.get('npm.install'), 'lnpm install %s' % plugin.module_name)} | **{plugin.name}**\n"
                          f"\n > **{plugin.desc}**\n"
                          f"\n > {ulang.get('npm.author')}: {plugin.author} | [🔗{ulang.get('npm.homepage')}]({plugin.homepage})\n\n***\n")
            if len(rs) > 10:
                reply += (f"\n{ulang.get('npm.too_many_results')}"
                          f"\n{button(ulang.get('npm.prev_page'), 'lnpm search %s %s' % (' '.join(keywords), 2))} | "
                          f"{button(ulang.get('npm.next_page'), 'lnpm search %s %s' % (' '.join(keywords), 2))}")
        else:
            reply = ulang.get("npm.search_no_result")
        await send_markdown(reply, bot, event=event)


async def npm_update() -> bool:
    """
    更新本地插件json缓存

    Returns:
        bool: 是否成功更新
    """
    url_list = [
            "https://registry.nonebot.dev/plugins.json",
    ]
    # 用aiohttp请求json文件，成功就覆盖本地文件，否则尝试下一个url
    for url in url_list:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open("data/liteyuki/plugins.json", "wb") as f:
                        data = await resp.read()
                        await f.write(data)
                        nonebot.logger.info()
                    return True
    return False


async def npm_search(keywords: list[str]) -> list[StorePlugin]:
    """
    搜索插件

    Args:
        keywords (list[str]): 关键词列表

    Returns:
        list[StorePlugin]: 插件列表
    """
    results = []
    async with aiofiles.open("data/liteyuki/plugins.json", "r", encoding="utf-8") as f:
        plugins: list[StorePlugin] = [StorePlugin(**pobj) for pobj in json.loads(await f.read())]
    for plugin in plugins:
        plugin_text = ' '.join(
            [
                    plugin.name,
                    plugin.desc,
                    plugin.author,
                    plugin.module_name,
                    plugin.project_link,
                    plugin.homepage,
                    ' '.join([tag.label for tag in plugin.tags])
            ]
        )
        if all([keyword in plugin_text for keyword in keywords]):
            results.append(plugin)
    return results


def install(plugin_name) -> bool:
    try:
        pip.main(['install', plugin_name])
        return True
    except Exception as e:
        print(e)
        return False
