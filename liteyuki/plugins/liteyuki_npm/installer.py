import os.path
import sys
from io import StringIO

import aiohttp
import nonebot
import pip
from arclet.alconna import Arparma, MultiVar
from nonebot import require
from nonebot.permission import SUPERUSER
from liteyuki.utils.language import get_user_lang
from liteyuki.utils.ly_typing import T_Bot
from liteyuki.utils.message import Markdown as md, send_markdown
from .common import *

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import Alconna, Args, Subcommand, on_alconna

npm_alc = on_alconna(
    Alconna(
        ["npm", "插件"],
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
            "uninstall",
            Args["plugin_name", str],
            alias=["rm", "移除", "卸载"],
        ),
        Subcommand(
            "list",
            alias=["l", "ls", "列表"],
        )
    ),
    permission=SUPERUSER
)


@npm_alc.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
    ulang = get_user_lang(str(event.user_id))

    if not os.path.exists("data/liteyuki/plugins.json"):
        await npm_update()

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
                btn_install = md.button(ulang.get("npm.install"), "npm install %s" % plugin.module_name)
                link_page = md.link(ulang.get("npm.homepage"), plugin.homepage)
                link_pypi = md.link(ulang.get("npm.pypi"), plugin.homepage)

                reply += (f"\n# **{plugin.name}**\n"
                          f"\n> **{plugin.desc}**\n"
                          f"\n> {ulang.get('npm.author')}: {plugin.author}"
                          f"\n> *{md.escape(plugin.module_name)}*"
                          f"\n> {btn_install}    {link_page}    {link_pypi}\n\n***\n")
            if len(rs) > max_show:
                reply += f"\n{ulang.get('npm.too_many_results', HIDE_NUM=len(rs) - max_show)}"
        else:
            reply = ulang.get("npm.search_no_result")
        await send_markdown(reply, bot, event=event)

    elif result.subcommands.get("install"):
        plugin_module_name: str = result.subcommands["install"].args.get("plugin_name")
        store_plugin = await get_store_plugin(plugin_module_name)
        await npm_alc.send(ulang.get("npm.installing", NAME=plugin_module_name))
        r, log = npm_install(plugin_module_name)
        log = log.replace("\\", "/")

        if not store_plugin:
            await npm_alc.finish(ulang.get("npm.plugin_not_found", NAME=plugin_module_name))

        homepage_btn = md.button(ulang.get("npm.homepage"), store_plugin.homepage)
        if r:

            r_load = nonebot.load_plugin(plugin_module_name)  # 加载插件
            installed_plugin = InstalledPlugin(module_name=plugin_module_name)  # 构造插件信息模型
            found_in_db_plugin = plugin_db.first(InstalledPlugin(), "module_name = ?", plugin_module_name)  # 查询数据库中是否已经安装

            if r_load:
                if found_in_db_plugin is None:
                    plugin_db.upsert(installed_plugin)
                    info = md.escape(ulang.get("npm.install_success", NAME=store_plugin.name))  # markdown转义
                    await send_markdown(
                        f"{info}\n\n"
                        f"```\n{log}\n```",
                        bot,
                        event=event
                    )
                else:
                    await npm_alc.finish(ulang.get("npm.plugin_already_installed", NAME=store_plugin.name))
            else:
                info = ulang.get("npm.load_failed", NAME=plugin_module_name, HOMEPAGE=homepage_btn).replace("_", r"\\_")
                await send_markdown(
                    f"{info}\n\n"
                    f"```\n{log}\n```\n",
                    bot,
                    event=event
                )
        else:
            info = ulang.get("npm.install_failed", NAME=plugin_module_name, HOMEPAGE=homepage_btn).replace("_", r"\\_")
            await send_markdown(
                f"{info}\n\n"
                f"```\n{log}\n```",
                bot,
                event=event
            )

    elif result.subcommands.get("uninstall"):
        plugin_module_name: str = result.subcommands["uninstall"].args.get("plugin_name")
        found_installed_plugin: InstalledPlugin = plugin_db.first(InstalledPlugin(), "module_name = ?", plugin_module_name)
        if found_installed_plugin:
            plugin_db.delete(InstalledPlugin, "module_name = ?", plugin_module_name)
            reply = f"{ulang.get('npm.uninstall_success', NAME=found_installed_plugin.module_name)}"
            await npm_alc.finish(reply)
        else:
            await npm_alc.finish(ulang.get("npm.plugin_not_installed", NAME=plugin_module_name))


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
                    ' '.join([tag.label for tag in plugin.tags])
            ]
        )
        if all([keyword in plugin_text for keyword in keywords]):
            results.append(plugin)
    return results


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
            "https://pypi.tuna.tsinghua.edu.cn/simple",  # 清华大学
            "https://pypi.mirrors.cqupt.edu.cn/simple",  # 重庆邮电大学
            "https://pypi.liteyuki.icu/simple",  # 轻雪镜像
            "https://pypi.org/simple",  # 官方源
    ]

    # 使用pip安装包，对每个镜像尝试一次，成功后返回值
    success = False
    for mirror in mirrors:
        try:
            nonebot.logger.info(f"npm_install try mirror: {mirror}")
            result = pip.main(["install", plugin_module_name, "-i", mirror])
            success = result == 0
            if success:
                break
            else:
                nonebot.logger.warning(f"npm_install failed, try next mirror.")
        except Exception as e:

            success = False
            continue

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    return success, buffer.getvalue()
