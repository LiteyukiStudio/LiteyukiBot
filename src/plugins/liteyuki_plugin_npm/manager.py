import nonebot.plugin
from nonebot import on_command
from nonebot.permission import SUPERUSER

from src.utils.adapter import T_MessageEvent
from src.utils.language import get_user_lang

list_plugins = on_command("list-plugin", aliases={"列出插件"}, priority=0)
toggle_plugin = on_command("enable-plugin", aliases={"启用插件", "禁用插件", "disable-plugin"}, priority=0)


@list_plugins.handle()
async def _(event: T_MessageEvent):
    lang = get_user_lang(str(event.user_id))
    reply = lang.get("npm.loaded_plugins")
    for plugin in nonebot.get_loaded_plugins():
        # 检查是否有 metadata 属性
        if plugin.metadata:
            reply += f"\n- {plugin.metadata.name}"
        else:
            reply += f"\n- {plugin.name}"
    await list_plugins.finish(reply)
