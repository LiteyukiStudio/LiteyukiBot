import nonebot.plugin
from nonebot import on_command
from nonebot.permission import SUPERUSER

from src.utils.data_manager import InstalledPlugin, plugin_db
from src.utils.message import Markdown as md, send_markdown
from src.utils.permission import GROUP_ADMIN, GROUP_OWNER
from src.utils.typing import T_Bot, T_MessageEvent
from src.utils.language import get_user_lang

list_plugins = on_command("list-plugin", aliases={"列出插件", "插件列表"}, priority=0)
toggle_plugin = on_command("enable-plugin", aliases={"启用插件", "停用插件", "disable-plugin"}, priority=0, permission=SUPERUSER)


@list_plugins.handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    lang = get_user_lang(str(event.user_id))
    reply = f"# {lang.get('npm.loaded_plugins')} | {lang.get('npm.total', TOTAL=len(nonebot.get_loaded_plugins()))} \n***"
    for plugin in nonebot.get_loaded_plugins():
        # 检查是否有 metadata 属性
        btn_help = md.button(lang.get('npm.help'), f'help {plugin.name}', False)
        reply += f"\n{btn_help} "
        if plugin.metadata:
            reply += (f"**{plugin.metadata.name}**\n"
                      f"\n > {plugin.metadata.description}")
        else:
            reply += (f"**{plugin.name}**\n"
                      f"\n > {lang.get('npm.no_description')}")
        # if await GROUP_ADMIN(bot=bot, event=event) or await GROUP_OWNER(bot=bot, event=event) or await SUPERUSER(bot=bot, event=event):
        if await GROUP_ADMIN(bot, event) or await GROUP_OWNER(bot, event) or await SUPERUSER(bot, event):
            btn_enable = md.button(lang.get('npm.enable'), f'enable-plugin {plugin.module_name}')
            btn_disable = md.button(lang.get('npm.disable'), f'disable-plugin {plugin.module_name}')
            reply += f"\n > {btn_enable}    {btn_disable}"
            if await SUPERUSER(bot, event):
                plugin_in_database = plugin_db.first(InstalledPlugin, 'module_name = ?', plugin.module_name)
                btn_remove = (
                        md.button(lang.get('npm.uninstall'), f'lnpm remove {plugin.module_name}')) if plugin_in_database else lang.get(
                    'npm.uninstall')
                reply += f"    {btn_remove}"
        reply += "\n\n***\n"
    await send_markdown(reply, bot, event=event)
