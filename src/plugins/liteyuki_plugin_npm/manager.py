import os

import nonebot.plugin
from nonebot import on_command
from nonebot.internal.matcher import Matcher
from nonebot.message import run_preprocessor
from nonebot.permission import SUPERUSER
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Arparma

from src.utils.data_manager import GroupChat, InstalledPlugin, User, group_db, plugin_db, user_db
from src.utils.message import Markdown as md, send_markdown
from src.utils.permission import GROUP_ADMIN, GROUP_OWNER
from src.utils.typing import T_Bot, T_MessageEvent
from src.utils.language import get_user_lang
from .common import get_plugin_can_be_toggle, get_plugin_current_enable, get_plugin_default_enable
from .installer import get_store_plugin, npm_update

list_plugins = on_command("list-plugin", aliases={"列出插件", "插件列表"}, priority=0)
# toggle_plugin = on_command("enable-plugin", aliases={"启用插件", "停用插件", "disable-plugin"}, priority=0)
toggle_plugin = on_alconna(
    Alconna(
        ['enable-plugin', 'disable-plugin'],
        Args['plugin_name', str]['global', bool, False],
    )
)


@list_plugins.handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    if not os.path.exists("data/liteyuki/plugins.json"):
        await npm_update()
    lang = get_user_lang(str(event.user_id))
    reply = f"# {lang.get('npm.loaded_plugins')} | {lang.get('npm.total', TOTAL=len(nonebot.get_loaded_plugins()))} \n***\n"
    for plugin in nonebot.get_loaded_plugins():
        # 检查是否有 metadata 属性
        # 添加帮助按钮
        btn_usage = md.button(lang.get('npm.usage'), f'help {plugin.name}', False)
        store_plugin = await get_store_plugin(plugin.module_name)

        if store_plugin:
            btn_homepage = md.link(lang.get('npm.homepage'), store_plugin.homepage)
        elif plugin.metadata and plugin.metadata.extra.get('liteyuki'):
            btn_homepage = md.link(lang.get('npm.homepage'), "https://github.com/snowykami/LiteyukiBot")
        else:
            btn_homepage = lang.get('npm.homepage')

        if plugin.metadata:
            reply += (f"\n**{md.escape(plugin.metadata.name)}**\n"
                      f"\n > {plugin.metadata.description}")
        else:
            reply += (f"**{md.escape(plugin.name)}**\n"
                      f"\n > {lang.get('npm.no_description')}")

        reply += f"\n > {btn_usage}  {btn_homepage}"

        if await GROUP_ADMIN(bot, event) or await GROUP_OWNER(bot, event) or await SUPERUSER(bot, event):
            # 添加启用/停用插件按钮
            btn_toggle = lang.get('npm.disable') if plugin.metadata and not plugin.metadata.extra.get('toggleable') \
                else md.button(lang.get('npm.disable'), f'enable-plugin {plugin.module_name}')
            reply += f"  {btn_toggle}"

            if await SUPERUSER(bot, event):
                plugin_in_database = plugin_db.first(InstalledPlugin, 'module_name = ?', plugin.module_name)
                # 添加移除插件
                btn_remove = (
                        md.button(lang.get('npm.uninstall'), f'npm remove {plugin.module_name}')) if plugin_in_database else lang.get(
                    'npm.uninstall')
                btn_toggle_global = lang.get('npm.disable') if plugin.metadata and not plugin.metadata.extra.get('toggleable') \
                    else md.button(lang.get('npm.disable_global'), f'disable-plugin {plugin.module_name} true')
                reply += f"  {btn_remove}  {btn_toggle_global}"

        reply += "\n\n***\n"
    await send_markdown(reply, bot, event=event)


@toggle_plugin.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
    if not os.path.exists("data/liteyuki/plugins.json"):
        await npm_update()
    # 判断会话类型
    ulang = get_user_lang(str(event.user_id))
    plugin_module_name = result.args.get("plugin_name")

    toggle = result.header_result == 'enable-plugin'  # 判断是启用还是停用
    current_enable = get_plugin_current_enable(event, plugin_module_name)  # 获取插件当前状态

    default_enable = get_plugin_default_enable(plugin_module_name)  # 获取插件默认状态
    can_be_toggled = get_plugin_can_be_toggle(plugin_module_name)  # 获取插件是否可以被启用/停用

    if not can_be_toggled:
        await toggle_plugin.finish(ulang.get("npm.plugin_cannot_be_toggled", NAME=plugin_module_name))

    if current_enable == toggle:
        await toggle_plugin.finish(
            ulang.get("npm.plugin_already", NAME=plugin_module_name, STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable")))

    if event.message_type == "private":
        session = user_db.first(User, "user_id = ?", event.user_id, default=User(user_id=event.user_id))
    else:
        if await GROUP_ADMIN(bot, event) or await GROUP_OWNER(bot, event) or await SUPERUSER(bot, event):
            session = group_db.first(GroupChat, "group_id = ?", event.group_id, default=GroupChat(group_id=event.group_id))
        else:
            return
    # 启用 已停用的默认启用插件 将其从停用列表移除
    # 启用 已停用的默认停用插件 将其放到启用列表
    # 停用 已启用的默认启用插件 将其放到停用列表
    # 停用 已启用的默认停用插件 将其从启用列表移除
    try:
        if toggle:
            if default_enable:
                session.disabled_plugins.remove(plugin_module_name)
            else:
                session.enabled_plugins.append(plugin_module_name)
        else:
            if default_enable:
                session.disabled_plugins.append(plugin_module_name)
            else:
                session.enabled_plugins.remove(plugin_module_name)
    except Exception as e:
        await toggle_plugin.finish(
            ulang.get(
                "npm.toggle_failed",
                NAME=plugin_module_name,
                STATUS=ulang.get("npm.enable") if toggle else ulang.get("npm.disable"),
                ERROR=str(e))
        )

    if event.message_type == "private":
        user_db.save(session)
    else:
        group_db.save(session)


@run_preprocessor
async def _(event: T_MessageEvent, matcher: Matcher):
    plugin = matcher.plugin
    nonebot.logger.info(f"Plugin: {plugin.module_name}")
