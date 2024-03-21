import json
import os.path
import shutil
import sys
from io import StringIO
from typing import Optional

import nonebot
from arclet.alconna import Arparma, MultiVar
from nonebot.permission import SUPERUSER
from nonebot.utils import run_sync
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand
import pip

import aiohttp, aiofiles
from typing_extensions import Any

from src.utils.language import get_user_lang
from src.utils.message import Markdown as md, send_markdown
from src.utils.resource import get_res
from src.utils.typing import T_Bot, T_MessageEvent

from .common import *

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
            alias=["s", "搜索"],
        ),
        Subcommand(
            "install",
            Args["plugin_name", str],
            alias=["i", "安装"],
        ),
        Subcommand(
            "remove",
            Args["plugin_name", str],
            alias=["rm", "移除", "卸载"],
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
        max_show = 10
        if len(rs):
            reply = f"{ulang.get('npm.search_result')} | {ulang.get('npm.total', TOTAL=len(rs))}\n***"
            for plugin in rs[:min(max_show, len(rs))]:
                btn_install = md.button(ulang.get('npm.install'), 'lnpm install %s' % plugin.module_name)
                link_page = md.link(ulang.get('npm.homepage'), plugin.homepage)

                reply += (f"\n{btn_install} | **{plugin.name}**\n"
                          f"\n > **{plugin.desc}**\n"
                          f"\n > {ulang.get('npm.author')}: {plugin.author} | {link_page}\n\n***\n")
            if len(rs) > max_show:
                reply += f"\n{ulang.get('npm.too_many_results')}"
        else:
            reply = ulang.get("npm.search_no_result")
        await send_markdown(reply, bot, event=event)

    elif result.subcommands.get("install"):
        plugin_name: str = result.subcommands["install"].args.get("plugin_name")
        r, log = npm_install(plugin_name)
        if r:
            nonebot.load_plugin(plugin_name)
            installed_plugin = InstalledPlugin(module_name=plugin_name)
            store_plugin = await get_store_plugin(plugin_name)
            plugin_db.save(installed_plugin)
            await send_markdown(
                f"**{ulang.get('npm.install_success', NAME=store_plugin.name)}**\n\n"
                f"```\n{log}\n```",
                bot,
                event=event
            )
        else:
            await send_markdown(
                f"{ulang.get('npm.install_success', NAME=plugin_name)}\n\n"
                f"```\n{log}\n```",
                bot,
                event=event
            )

    elif result.subcommands.get("remove"):
        plugin_name: str = result.subcommands["remove"].args.get("plugin_name")
        await npm_alc.finish(ulang.get("npm.remove_success"))


async def npm_update() -> bool:
    """
    更新本地插件json缓存

    Returns:
        bool: 是否成功更新
    """
    url_list = [
            "https://registry.nonebot.dev/plugins.json",
    ]
    for url in url_list:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    async with aiofiles.open("data/liteyuki/plugins.json", "wb") as f:
                        data = await resp.read()
                        await f.write(data)
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


async def get_store_plugin(plugin_module_name: str) -> Optional[StorePlugin]:
    """
    获取插件信息

    Args:
        plugin_module_name (str): 插件模块名

    Returns:
        Optional[StorePlugin]: 插件信息
    """
    async with aiofiles.open("data/liteyuki/plugins.json", "r", encoding="utf-8") as f:
        plugins: list[StorePlugin] = [StorePlugin(**pobj) for pobj in json.loads(await f.read())]
    for plugin in plugins:
        if plugin.module_name == plugin_module_name:
            return plugin
    return None


def npm_install(plugin_module_name) -> tuple[bool, str]:
    """
    Args:
        plugin_module_name:

    Returns:
        tuple[bool, str]:

    """
    buffer = StringIO()
    sys.stdout = buffer
    sys.stderr = buffer

    mirrors = [
            "https://pypi.tuna.tsinghua.edu.cn/simple",
            "https://pypi.mirrors.cqupt.edu.cn/simple/",
            "https://pypi.org/simple",
    ]

    # 使用pip安装包，对每个镜像尝试一次，成功后返回值
    success = False
    for mirror in mirrors:
        try:
            result = pip.main(['install', plugin_module_name, "-i", mirror])
            success = result == 0
            break
        except Exception as e:
            success = False
            continue

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    return success, buffer.getvalue()
