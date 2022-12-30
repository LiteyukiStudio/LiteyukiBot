import traceback

import nonebot
from nonebot import get_driver
from nonebot import on_command
from nonebot import plugin
from nonebot.adapters.onebot.v11 import Bot, Message, GROUP_OWNER, GROUP_ADMIN, PRIVATE_FRIEND
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.utils import run_sync
from ...liteyuki_api.reloader import Reloader
from ...liteyuki_api.utils import download_file, Command

driver = get_driver()
from .plugin_api import *

bot_help = on_command(cmd="help", aliases={"帮助", "列出插件", "插件列表", "全部插件"})
enable_plugin = on_command(cmd="启用", aliases={"停用"}, permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN | PRIVATE_FRIEND)
add_meta_data = on_command(cmd="添加插件元数据", permission=SUPERUSER)
del_meta_data = on_command(cmd="删除插件元数据", permission=SUPERUSER)
hidden_plugin = on_command(cmd="隐藏插件", permission=SUPERUSER)
install_plugin = on_command("#install", aliases={"#安装插件"}, permission=SUPERUSER)
uninstall_plugin = on_command("#uninstall", aliases={"#卸载插件"}, permission=SUPERUSER)
update_metadata = on_command("#更新元数据", permission=SUPERUSER)


@bot_help.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    if str(arg).strip() == "":
        try:
            if event.raw_message.strip() == "全部插件":
                raise KeyError("全部插件")
            canvas = generate_plugin_image(event)
            file = canvas.export_cache()
            msg = MessageSegment.image(file="file:///%s" % file)
            await bot_help.send(message=msg)
            canvas.delete()
        except BaseException as e:
            print(e.__repr__())
            traceback.format_exception(e)
            _hidden_plugin = Data(Data.globals, "plugin_data").get_data(key="hidden_plugin", default=[])
            msg = "加载插件数：%s" % len(plugin.get_loaded_plugins())
            for _plugin in plugin.get_loaded_plugins():
                hidden_stats = "隐" if _plugin.name in _hidden_plugin else "显"
                enable_stats = "开" if check_enabled_stats(event, _plugin.name) else "关"
                if _plugin.metadata is not None:
                    p_name = _plugin.metadata.name
                else:
                    if metadata_db.get_data(_plugin.name) is not None:
                        p_name = PluginMetadata(**metadata_db.get_data(_plugin.name)).name
                    else:
                        p_name = _plugin.name
                msg += "\n[%s|%s]%s" % (enable_stats, hidden_stats, p_name)
            msg += "\n•使用「help插件名」来获取对应插件的使用方法\n"
            await bot_help.send(message=msg)
    else:
        plugin_name_input = str(arg).strip()
        plugin_ = search_for_plugin(plugin_name_input)
        if plugin_ is None:
            await bot_help.finish("插件不存在", at_sender=True)
        else:
            if plugin_.metadata is not None or metadata_db.get_data(plugin_.name) is not None:
                if metadata_db.get_data(plugin_.name) is not None:
                    plugin_.metadata = PluginMetadata(**metadata_db.get_data(plugin_.name))
                await bot_help.finish("•%s\n「%s」\n==========\n使用方法\n%s" % (plugin_.metadata.name, plugin_.metadata.description, str(plugin_.metadata.usage)))
            else:
                await bot_help.finish("%s还没有编写使用方法" % plugin_.name)


@enable_plugin.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    plugin_name_input = str(arg)
    enable = True if event.raw_message.strip().startswith("启用") else False
    searched_plugin = search_for_plugin(plugin_name_input)
    if searched_plugin is not None:
        if searched_plugin.metadata is None:
            show_name = searched_plugin.name
            force_enable = False
            if metadata_db.get_data(searched_plugin.name) is not None:
                custom_plugin_metadata = PluginMetadata(**metadata_db.get_data(searched_plugin.name))
                show_name = custom_plugin_metadata.name
                force_enable = custom_plugin_metadata.extra.get("force_enable", False)
        else:
            show_name = searched_plugin.metadata.name
            force_enable = searched_plugin.metadata.extra.get("force_enable", False)
        stats = check_enabled_stats(event, searched_plugin.name)
        if force_enable:
            await enable_plugin.finish("「%s」处于强制启用状态，无法更改" % show_name, at_sender=True)
        if stats == enable:
            await enable_plugin.finish("「%s」处于%s状态，无需重复操作" % (show_name, "启用" if stats else "停用"), at_sender=True)
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
            await enable_plugin.finish("「%s」%s成功" % (show_name, "启用" if enable else "停用"), at_sender=True)
    else:
        await enable_plugin.finish("插件不存在", at_sender=True)


@add_meta_data.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    arg = Command.escape(str(arg))
    arg_line = arg.splitlines()
    plugin_name_input = arg_line[0]
    _plugin = search_for_plugin(plugin_name_input)
    if _plugin is None:
        await add_meta_data.send("插件不存在", at_sender=True)
    if _plugin.metadata is not None:
        await add_meta_data.send("插件源码中已存在元数据", at_sender=True)
    meta_data = {"name": arg_line[1], "description": arg_line[2], "usage": "\n".join(arg_line[3:])}
    Data(Data.globals, "plugin_metadata").set_data(_plugin.name, meta_data)
    await add_meta_data.send("「%s」元数据添加成功" % _plugin.name, at_sender=True)


@del_meta_data.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    arg = Command.escape(str(arg))
    _plugin = search_for_plugin(arg)
    if _plugin is None:
        await del_meta_data.send("插件不存在", at_sender=True)
    elif _plugin.metadata is not None:
        await del_meta_data.send("插件源码中已存在元数据", at_sender=True)
    elif metadata_db.get_data(_plugin.name) is None:
        await del_meta_data.send("插件中不存在自定义元数据", at_sender=True)
    else:
        metadata_db.del_data(_plugin.name)
        await del_meta_data.send("「%s」元数据删除成功" % _plugin.name, at_sender=True)


@hidden_plugin.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    arg = Command.escape(str(arg))
    plugin_name_input = arg
    _plugin = search_for_plugin(plugin_name_input)
    if _plugin is None:
        await hidden_plugin.finish("插件不存在", at_sender=True)
    else:
        _hidden_plugin = Data(Data.globals, "plugin_data").get_data(key="hidden_plugin", default=[])
        _hidden_plugin.append(_plugin.name)
        _hidden_plugin = set(_hidden_plugin)
        Data(Data.globals, "plugin_data").set_data(key="hidden_plugin", value=list(_hidden_plugin))
        await hidden_plugin.send("「%s」隐藏成功" % _plugin.name, at_sender=True)


@install_plugin.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    args = str(arg).strip().split()
    suc = False
    for plugin_name in args:
        try:
            _plugins = search_plugin_info_online(plugin_name)
            if _plugins is None:
                await install_plugin.send("在Nonebot商店中找不到插件：%s" % plugin_name)
            else:
                _plugin = _plugins[0]
                await install_plugin.send("正在尝试安装插件：%s(%s)" % (_plugin["name"], _plugin["id"]))
                result = (await run_sync(os.popen)("nb plugin install %s" % _plugin["id"])).read()
                if "Successfully installed" in result.splitlines()[-1]:
                    await install_plugin.send("插件：%s(%s)安装成功" % (_plugin["name"], _plugin["id"]))
                    suc = True
                elif "Requirement already satisfied" in result.splitlines()[-1]:
                    await install_plugin.send("已安装过%s(%s)，无法重复安装" % (_plugin["name"], _plugin["id"]))
                else:
                    await install_plugin.send("安装过程可能出现问题：%s" % result)
        except BaseException as e:
            await install_plugin.send("安装%s时出现错误:%s" % (plugin_name, traceback.format_exc()))
    if suc:
        await install_plugin.send("安装过程结束，正在重启...")
        Reloader.reload()


@driver.on_bot_connect
async def detect_liteyuki_resource():
    """
    检测轻雪插件的资源，不存在就下载
    :return:
    """
    mirror = "https://ghproxy.com/https://github.com/"
    for _plugin in get_loaded_plugins():
        if _plugin.metadata is not None and _plugin.metadata.extra.get("liteyuki_plugin", False):
            git_resource = _plugin.metadata.extra.get("liteyuki_resource_git", {})
            for root_path, url in git_resource.items():
                if not os.path.exists(os.path.join(Path.root, root_path)):
                    await run_sync(download_file)(file=os.path.join(Path.root, root_path), url=mirror + url)
            normal_resource = _plugin.metadata.extra.get("liteyuki_resource", {})
            for root_path, url in git_resource.items():
                if not os.path.exists(os.path.join(Path.root, root_path)):
                    await run_sync(download_file)(file=os.path.join(Path.root, root_path), url=url)


@driver.on_bot_connect
async def update_metadata():
    """
    联网在nb商店中获取插件元数据

    :return:
    """
    for p in get_loaded_plugins():
        try:
            if p.metadata is None and metadata_db.get_data(p.name) is None:
                plugin_data = await run_sync(search_plugin_info_online)(p.name)
                if plugin_data is not None:
                    plugin_data = plugin_data[0]
                    metadata_db.set_data(p.name, {"name": plugin_data["name"], "description": plugin_data["description"], "usage": ""})
                    nonebot.logger.info("已从Nonebot插件商店中更新本地插件%s（%s）的信息" % (plugin_data["name"], p.name))
        except BaseException as e:
            nonebot.logger.info("更新插件%s信息时出现错误:%s" % (p.name, traceback.format_exception(e)))
