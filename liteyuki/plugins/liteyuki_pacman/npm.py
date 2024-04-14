import os
import sys
import aiohttp
import nonebot.plugin
import pip
from io import StringIO
from arclet.alconna import MultiVar
from nonebot import Bot, require
from nonebot.exception import FinishedException, IgnoredException, MockApiException
from nonebot.internal.adapter import Event
from nonebot.internal.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.permission import SUPERUSER
from nonebot.plugin import Plugin
from liteyuki.utils.base.data_manager import InstalledPlugin
from liteyuki.utils.base.language import get_user_lang
from liteyuki.utils.base.ly_typing import T_Bot
from liteyuki.utils.message.message import MarkdownMessage as md
from liteyuki.utils.base.permission import GROUP_ADMIN, GROUP_OWNER
from liteyuki.utils.message.tools import clamp
from .common import *

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Arparma, Subcommand

# const
enable_global = "enable-global"
disable_global = "disable-global"
enable = "enable"
disable = "disable"


@on_alconna(
    aliases={"插件"},
    command=Alconna(
        "npm",
        Subcommand(
            "enable",
            Args["plugin_name", str],
            alias=["e", "启用"],
        ),
        Subcommand(
            "disable",
            Args["plugin_name", str],
            alias=["d", "停用"],
        ),
        Subcommand(
            enable_global,
            Args["plugin_name", str],
            alias=["eg", "全局启用"],
        ),
        Subcommand(
            disable_global,
            Args["plugin_name", str],
            alias=["dg", "全局停用"],
        ),
        # 安装部分
        Subcommand(
            "update",
            alias=["u", "更新"],
        ),
        Subcommand(
            "search",
            Args["keywords", MultiVar(str)],
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
            alias=["r", "rm", "卸载"],
        ),
        Subcommand(
            "list",
            Args["page", int, 1]["num", int, 10],
            alias=["ls", "列表"],
        )
    )
).handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot, npm: Matcher):
    if not os.path.exists("data/liteyuki/plugins.json"):
        await npm_update()
    # 判断会话类型
    ulang = get_user_lang(str(event.user_id))
    plugin_name = result.args.get("plugin_name")
    sc = result.subcommands  # 获取子命令
    perm_s = await SUPERUSER(bot, event)  # 判断是否为超级用户
    # 支持对自定义command_start的判断
    if sc.get("enable") or result.subcommands.get("disable"):

        toggle = result.subcommands.get("enable") is not None

        plugin_exist = get_plugin_exist(plugin_name)

        session_enable = get_plugin_session_enable(event, plugin_name)  # 获取插件当前状态

        default_enable = get_plugin_default_enable(plugin_name)  # 获取插件默认状态

        can_be_toggled = get_plugin_can_be_toggle(plugin_name)  # 获取插件是否可以被启用/停用

        if not plugin_exist:
            await npm.finish(ulang.get("npm.plugin_not_found", NAME=plugin_name))

        if not can_be_toggled:
            await npm.finish(ulang.get("npm.plugin_cannot_be_toggled", NAME=plugin_name))

        if session_enable == toggle:
            await npm.finish(
                ulang.get("npm.plugin_already", NAME=plugin_name, STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable")))

        if event.message_type == "private":
            session = user_db.first(User(), "user_id = ?", event.user_id, default=User(user_id=event.user_id))
        else:
            if await GROUP_ADMIN(bot, event) or await GROUP_OWNER(bot, event) or await SUPERUSER(bot, event):
                session = group_db.first(Group(), "group_id = ?", event.group_id, default=Group(group_id=str(event.group_id)))
            else:
                raise FinishedException(ulang.get("Permission Denied"))
        try:
            if toggle:
                if default_enable:
                    session.disabled_plugins.remove(plugin_name)
                else:
                    session.enabled_plugins.append(plugin_name)
            else:
                if default_enable:
                    session.disabled_plugins.append(plugin_name)
                else:
                    session.enabled_plugins.remove(plugin_name)
            if event.message_type == "private":
                user_db.upsert(session)
            else:
                group_db.upsert(session)
        except Exception as e:
            print(e)
            await npm.finish(
                ulang.get(
                    "npm.toggle_failed",
                    NAME=plugin_name,
                    STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable"),
                    ERROR=str(e))
            )

        await npm.finish(
            ulang.get(
                "npm.toggle_success",
                NAME=plugin_name,
                STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable"))
        )

    elif sc.get(enable_global) or result.subcommands.get(disable_global) and await SUPERUSER(bot, event):
        plugin_exist = get_plugin_exist(plugin_name)

        toggle = result.subcommands.get(enable_global) is not None

        can_be_toggled = get_plugin_can_be_toggle(plugin_name)

        if not plugin_exist:
            await npm.finish(ulang.get("npm.plugin_not_found", NAME=plugin_name))

        if not can_be_toggled:
            await npm.finish(ulang.get("npm.plugin_cannot_be_toggled", NAME=plugin_name))

        global_enable = get_plugin_global_enable(plugin_name)
        if global_enable == toggle:
            await npm.finish(
                ulang.get("npm.plugin_already", NAME=plugin_name, STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable")))

        try:
            storePlugin = plugin_db.first(GlobalPlugin(), "module_name = ?", plugin_name, default=GlobalPlugin(module_name=plugin_name))
            if toggle:
                storePlugin.enabled = True
            else:
                storePlugin.enabled = False
            plugin_db.upsert(storePlugin)
        except Exception as e:
            print(e)
            await npm.finish(
                ulang.get(
                    "npm.toggle_failed",
                    NAME=plugin_name,
                    STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable"),
                    ERROR=str(e))
            )

        await npm.finish(
            ulang.get(
                "npm.toggle_success",
                NAME=plugin_name,
                STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable"))
        )

    elif sc.get("update") and perm_s:
        r = await npm_update()
        if r:
            await npm.finish(ulang.get("npm.store_update_success"))
        else:
            await npm.finish(ulang.get("npm.store_update_failed"))

    elif sc.get("search"):
        keywords: list[str] = result.subcommands["search"].args.get("keywords")
        rs = await npm_search(keywords)
        max_show = result.subcommands.get("search").args.get("show_num")
        if len(rs):
            reply = f"{ulang.get('npm.search_result')} | {ulang.get('npm.total', TOTAL=len(rs))}\n***"
            for storePlugin in rs[:min(max_show, len(rs))]:
                btn_install_or_update = md.btn_cmd(
                    ulang.get("npm.update") if get_plugin_exist(storePlugin.module_name) else ulang.get("npm.install"),
                    "npm install %s" % storePlugin.module_name
                )
                link_page = md.btn_link(ulang.get("npm.homepage"), storePlugin.homepage)
                link_pypi = md.btn_link(ulang.get("npm.pypi"), storePlugin.homepage)

                reply += (f"\n# **{storePlugin.name}**\n"
                          f"\n> **{storePlugin.desc}**\n"
                          f"\n> {ulang.get('npm.author')}: {storePlugin.author}"
                          f"\n> *{md.escape(storePlugin.module_name)}*"
                          f"\n> {btn_install_or_update}    {link_page}    {link_pypi}\n\n***\n")
            if len(rs) > max_show:
                reply += f"\n{ulang.get('npm.too_many_results', HIDE_NUM=len(rs) - max_show)}"
        else:
            reply = ulang.get("npm.search_no_result")
        await md.send_md(reply, bot, event=event)

    elif sc.get("install") and perm_s:
        plugin_name: str = result.subcommands["install"].args.get("plugin_name")
        store_plugin = await get_store_plugin(plugin_name)
        await npm.send(ulang.get("npm.installing", NAME=plugin_name))
        r, log = npm_install(plugin_name)
        log = log.replace("\\", "/")

        if not store_plugin:
            await npm.finish(ulang.get("npm.plugin_not_found", NAME=plugin_name))

        homepage_btn = md.btn_cmd(ulang.get("npm.homepage"), store_plugin.homepage)
        if r:

            r_load = nonebot.load_plugin(plugin_name)  # 加载插件
            installed_plugin = InstalledPlugin(module_name=plugin_name)  # 构造插件信息模型
            found_in_db_plugin = plugin_db.first(InstalledPlugin(), "module_name = ?", plugin_name)  # 查询数据库中是否已经安装

            if r_load:
                if found_in_db_plugin is None:
                    plugin_db.upsert(installed_plugin)
                    info = md.escape(ulang.get("npm.install_success", NAME=store_plugin.name))  # markdown转义
                    await md.send_md(
                        f"{info}\n\n"
                        f"```\n{log}\n```",
                        bot,
                        event=event
                    )
                else:
                    await npm.finish(ulang.get("npm.plugin_already_installed", NAME=store_plugin.name))
            else:
                info = ulang.get("npm.load_failed", NAME=plugin_name, HOMEPAGE=homepage_btn).replace("_", r"\\_")
                await md.send_md(
                    f"{info}\n\n"
                    f"```\n{log}\n```\n",
                    bot,
                    event=event
                )
        else:
            info = ulang.get("npm.install_failed", NAME=plugin_name, HOMEPAGE=homepage_btn).replace("_", r"\\_")
            await md.send_md(
                f"{info}\n\n"
                f"```\n{log}\n```",
                bot,
                event=event
            )

    elif sc.get("uninstall") and perm_s:
        plugin_name: str = result.subcommands["uninstall"].args.get("plugin_name")
        found_installed_plugin: InstalledPlugin = plugin_db.first(InstalledPlugin(), "module_name = ?", plugin_name)
        if found_installed_plugin:
            plugin_db.delete(InstalledPlugin(), "module_name = ?", plugin_name)
            reply = f"{ulang.get('npm.uninstall_success', NAME=found_installed_plugin.module_name)}"
            await npm.finish(reply)
        else:
            await npm.finish(ulang.get("npm.plugin_not_installed", NAME=plugin_name))

    elif sc.get("list"):
        loaded_plugin_list = sorted(nonebot.get_loaded_plugins(), key=lambda x: x.name)
        num_per_page = result.subcommands.get("list").args.get("num")
        total = len(loaded_plugin_list) // num_per_page + (1 if len(loaded_plugin_list) % num_per_page else 0)

        page = clamp(result.subcommands.get("list").args.get("page"), 1, total)

        # 已加载插件 | 总计10 | 第1/3页
        reply = (f"# {ulang.get('npm.loaded_plugins')} | "
                 f"{ulang.get('npm.total', TOTAL=len(nonebot.get_loaded_plugins()))} | "
                 f"{ulang.get('npm.page', PAGE=page, TOTAL=total)} \n***\n")

        permission_oas = await GROUP_ADMIN(bot, event) or await GROUP_OWNER(bot, event) or await SUPERUSER(bot, event)
        permission_s = await SUPERUSER(bot, event)

        for storePlugin in loaded_plugin_list[(page - 1) * num_per_page: min(page * num_per_page, len(loaded_plugin_list))]:
            # 检查是否有 metadata 属性
            # 添加帮助按钮

            btn_usage = md.btn_cmd(ulang.get("npm.usage"), f"help {storePlugin.name}", False)
            store_plugin = await get_store_plugin(storePlugin.name)
            session_enable = get_plugin_session_enable(event, storePlugin.name)
            if store_plugin:
                btn_homepage = md.btn_link(ulang.get("npm.homepage"), store_plugin.homepage)
                show_name = store_plugin.name
            elif storePlugin.metadata:
                if storePlugin.metadata.extra.get("liteyuki"):
                    btn_homepage = md.btn_link(ulang.get("npm.homepage"), "https://github.com/snowykami/LiteyukiBot")
                else:
                    btn_homepage = ulang.get("npm.homepage")
                show_name = storePlugin.metadata.name
            else:
                btn_homepage = ulang.get("npm.homepage")
                show_name = storePlugin.name
                ulang.get("npm.no_description")

            if storePlugin.metadata:
                reply += f"\n**{md.escape(show_name)}**\n"
            else:
                reply += f"**{md.escape(show_name)}**\n"

            reply += f"\n > {btn_usage}  {btn_homepage}"

            if permission_oas:
                # 添加启用/停用插件按钮
                cmd_toggle = f"npm {'disable' if session_enable else 'enable'} {storePlugin.name}"
                text_toggle = ulang.get("npm.disable" if session_enable else "npm.enable")
                can_be_toggle = get_plugin_can_be_toggle(storePlugin.name)
                btn_toggle = text_toggle if not can_be_toggle else md.btn_cmd(text_toggle, cmd_toggle)
                reply += f"  {btn_toggle}"

                if permission_s:
                    plugin_in_database = plugin_db.first(InstalledPlugin(), "module_name = ?", storePlugin.name)
                    # 添加移除插件和全局切换按钮
                    global_enable = get_plugin_global_enable(storePlugin.name)
                    btn_uninstall = (
                            md.btn_cmd(ulang.get("npm.uninstall"), f'npm uninstall {storePlugin.name}')) if plugin_in_database else ulang.get(
                        'npm.uninstall')
                    btn_toggle_global_text = ulang.get("npm.disable_global" if global_enable else "npm.enable_global")
                    cmd_toggle_global = f"npm {'disable' if global_enable else 'enable'}-global {storePlugin.name}"
                    btn_toggle_global = btn_toggle_global_text if not can_be_toggle else md.btn_cmd(btn_toggle_global_text, cmd_toggle_global)

                    reply += f"  {btn_uninstall}  {btn_toggle_global}"
            reply += "\n\n***\n"
        await md.send_md(reply, bot, event=event)

    else:
        await npm.finish(ulang.get("liteyuki.invalid_command"))


@on_alconna(
    aliases={"群聊"},
    command=Alconna(
        "gm",
        Subcommand(
            enable,
            Args["group_id", str, None],
            alias=["e", "启用"],
        ),
        Subcommand(
            disable,
            Args["group_id", str, None],
            alias=["d", "停用"],
        ),
    ),
    permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN
).handle()
async def _(bot: T_Bot, event: T_MessageEvent, gm: Matcher, result: Arparma):
    ulang = get_user_lang(str(event.user_id))
    to_enable = result.subcommands.get(enable) is not None
    group_id = None
    if await SUPERUSER(bot, event):
        # 仅超级用户可以自定义群号
        group_id = result.subcommands.get(enable, result.subcommands.get(disable)).args.get("group_id")

    if group_id is None and event.message_type == "group":
        group_id = str(event.group_id)
    else:
        await gm.finish(ulang.get("liteyuki.invalid_command"), liteyuki_pass=True)

    enabled = get_group_enable(group_id)
    if enabled == to_enable:
        await gm.finish(ulang.get("liteyuki.group_already", STATUS=ulang.get("npm.enable") if to_enable else ulang.get("npm.disable"), GROUP=group_id),
                        liteyuki_pass=True)
    else:
        group: Group = group_db.first(Group(), "group_id = ?", group_id, default=Group(group_id=group_id))
        if to_enable:
            group.enable = True
        else:
            group.enable = False
        group_db.upsert(group)
        await gm.finish(
            ulang.get("liteyuki.group_success", STATUS=ulang.get("npm.enable") if to_enable else ulang.get("npm.disable"), GROUP=group_id),
            liteyuki_pass=True
        )


@run_preprocessor
async def pre_handle(event: Event, matcher: Matcher):
    plugin: Plugin = matcher.plugin
    plugin_global_enable = get_plugin_global_enable(plugin.name)
    if not plugin_global_enable:
        raise IgnoredException("Plugin disabled globally")
    if event.get_type() == "message":
        plugin_session_enable = get_plugin_session_enable(event, plugin.name)
        if not plugin_session_enable:
            raise IgnoredException("Plugin disabled in session")


@Bot.on_calling_api
async def block_disable_session(bot: Bot, api: str, args: dict):
    if "group_id" in args and not args.get("liteyuki_pass", False):
        group_id = args["group_id"]
        if not get_group_enable(group_id):
            nonebot.logger.debug(f"Group {group_id} disabled")
            raise MockApiException(f"Group {group_id} disabled")


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


def npm_install(plugin_package_name) -> tuple[bool, str]:
    """
    Args:
        plugin_package_name:

    Returns:
        tuple[bool, str]: 是否成功，输出信息

    """
    # 重定向标准输出
    buffer = StringIO()
    sys.stdout = buffer
    sys.stderr = buffer

    update = False
    if get_plugin_exist(plugin_package_name):
        update = True

    mirrors = [
            "https://pypi.tuna.tsinghua.edu.cn/simple",  # 清华大学
            "https://pypi.org/simple",  # 官方源
    ]

    # 使用pip安装包，对每个镜像尝试一次，成功后返回值
    success = False
    for mirror in mirrors:
        try:
            nonebot.logger.info(f"pip install try mirror: {mirror}")
            if update:
                result = pip.main(["install", "--upgrade", plugin_package_name, "-i", mirror])
            else:
                result = pip.main(["install", plugin_package_name, "-i", mirror])
            success = result == 0
            if success:
                break
            else:
                nonebot.logger.warning(f"pip install failed, try next mirror.")
        except Exception as e:
            success = False
            continue

    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__

    return success, buffer.getvalue()
