from typing import Union

from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, PrivateMessageEvent, Message, GROUP_OWNER, GROUP_ADMIN
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.typing import T_State
from nonebot import plugin
from .plugin_api import *

bot_help = on_command(cmd="help", aliases={"帮助", "列出插件"})
enable_plugin = on_command(cmd="启用", aliases={"停用"}, permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN)


@bot_help.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    msg = "插件列表如下"
    for p in plugin.get_loaded_plugins():
        if p.metadata is not None:
            msg += "\n[%s]%s" % ("启用" if check_enabled_stats(event, p.name) else "停用", p.metadata.name)
        else:
            msg += "\n[%s]%s" % ("启用" if check_enabled_stats(event, p.name) else "停用", p.name)
    await bot_help.send(message=msg)


@enable_plugin.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    plugin_name_input = str(arg)
    enable = True if event.raw_message.strip().startswith("启用") else False
    searched_plugin = search_for_plugin(plugin_name_input)
    if searched_plugin is not None:
        if searched_plugin.metadata is None:
            show_name = searched_plugin.name
            force_enable = False
        else:
            show_name = searched_plugin.metadata.name
            force_enable = searched_plugin.metadata.extra.get("force_enable", False)
        stats = check_enabled_stats(event, searched_plugin.name)
        if force_enable:
            await enable_plugin.finish("%s处于强制启用状态，无法更改" % show_name, at_sender=True)
        if stats == enable:
            await enable_plugin.finish("%s处于%s状态，无需重复操作" % (show_name, "启用" if stats else "停用"), at_sender=True)
        else:
            db = Data(*Data.get_type_id(event))
            enabled_plugin = db.get_data("enabled_plugin", [])
            disabled_plugin = db.get_data("disabled_plugin", [])
            default_stats = get_plugin_default_stats(searched_plugin.name)
            if default_stats:
                if enable:
                    disabled_plugin.remove(searched_plugin.name)
                else:
                    disabled_plugin.append(searched_plugin.name)
            else:
                if enable:
                    enabled_plugin.append(searched_plugin.name)
                else:
                    enabled_plugin.remove(searched_plugin.name)
            db.set_data(key="enabled_plugin", value=enabled_plugin)
            db.set_data(key="disabled_plugin", value=disabled_plugin)
            await enable_plugin.finish("%s%s成功" % (show_name, "启用" if enable else "停用"), at_sender=True)
    else:
        await enable_plugin.finish("插件不存在", at_sender=True)
