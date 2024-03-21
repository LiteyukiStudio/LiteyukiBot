import nonebot.plugin
from nonebot import on_command
from nonebot.permission import SUPERUSER

from src.utils.message import Markdown as md, send_markdown
from src.utils.typing import T_Bot, T_MessageEvent
from src.utils.language import get_user_lang

list_plugins = on_command("list-plugin", aliases={"列出插件", "插件列表"}, priority=0, permission=SUPERUSER)
toggle_plugin = on_command("enable-plugin", aliases={"启用插件", "禁用插件", "disable-plugin"}, priority=0, permission=SUPERUSER)


@list_plugins.handle()
async def _(event: T_MessageEvent, bot: T_Bot):
    lang = get_user_lang(str(event.user_id))
    reply = f"# {lang.get('npm.loaded_plugins')} | {lang.get('npm.total', TOTAL=len(nonebot.get_loaded_plugins()))} \n***"
    for plugin in nonebot.get_loaded_plugins():
        # 检查是否有 metadata 属性
        if plugin.metadata:
            reply += (f"\n{md.button(lang.get('npm.help'), 'help %s' % plugin.name, False, False)} "
                      f"**{plugin.metadata.name}**\n"
                      f"\n > {plugin.metadata.description}\n\n***\n")
        else:
            reply += (f"\n{md.button(lang.get('npm.help'), 'help %s' % plugin.name, False, False)} "
                      f"**{plugin.name}**\n"
                      f"\n > {lang.get('npm.no_description')}\n\n***\n")
    await send_markdown(reply, bot, event=event)
