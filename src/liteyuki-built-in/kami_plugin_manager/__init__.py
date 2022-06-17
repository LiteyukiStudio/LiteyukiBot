from nonebot import on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Bot, GROUP_ADMIN, GROUP_OWNER, PRIVATE_FRIEND, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
# 插件开关
# 插件详情
# 插件帮助
from nonebot.typing import T_State
from .autorun import *
from ...extraApi.base import Command, Session
from ...extraApi.permission import MASTER, AUTHUSER
from ...extraApi.plugin import *
from ...extraApi.rule import *

enablePlugin = on_command(cmd="启用插件", aliases={"停用插件", "开启插件", "关闭插件"}, permission=SUPERUSER | MASTER | GROUP_ADMIN | GROUP_OWNER | AUTHUSER, priority=1, block=True)

listPlugin = on_command(cmd="列出插件", aliases={"菜单", "menu", "help", "帮助"}, rule=check_plugin_enable("kami_plugin_manager"), priority=1, block=True)
createPlugin = on_command(cmd="创建插件", priority=10, block=True, permission=SUPERUSER | MASTER)


@enablePlugin.handle()
async def enablePluginHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State, args: Message = CommandArg()):
    try:
        plugin: Plugin = searchForPlugin(str(args))
        if plugin is not None:
            pluginState = await getPluginEnable(event.message_type, ExtraData.getTargetId(event), plugin)
            operation = True if event.raw_message.strip()[0:4] in ["启用插件", "开启插件"] else False
            if type(event) is GroupMessageEvent and await (GROUP_OWNER | GROUP_ADMIN | SUPERUSER)(bot, event) or type(event) is PrivateMessageEvent:
                bannedPlugin: list = await ExtraData.getData(targetType=event.message_type,
                                                             targetId=ExtraData.getTargetId(event),
                                                             key="banned_plugin",
                                                             default=[])
                enabledPlugin: list = await ExtraData.getData(targetType=event.message_type,
                                                              targetId=ExtraData.getTargetId(event),
                                                              key="enabled_plugin",
                                                              default=[])
                if pluginState != operation:
                    await enablePlugin.send(
                        message="%s(%s) %s成功!" % (plugin.pluginName, plugin.pluginId, "启用" if operation else "停用"))
                    if operation:
                        # 启用
                        if plugin.defaultStats:
                            bannedPlugin.remove(plugin.pluginId)
                        else:
                            enabledPlugin.append(plugin.pluginId)
                    else:
                        if plugin.defaultStats:
                            bannedPlugin.append(plugin.pluginId)
                        else:
                            enabledPlugin.remove(plugin.pluginId)
                    await ExtraData.setData(event.message_type, ExtraData.getTargetId(event), key="banned_plugin",
                                            value=bannedPlugin)
                    await ExtraData.setData(event.message_type, ExtraData.getTargetId(event), key="enabled_plugin",
                                            value=enabledPlugin)
                else:
                    await enablePlugin.send(message="%s(%s) %s中, 无需重复操作!" % (
                        plugin.pluginName, plugin.pluginId, "启用" if operation else "停用"))
        else:
            await enablePlugin.send(
                "插件:%s不存在" % Command.formatToString(*Command.formatToCommand(event.raw_message.strip())[0][1:]),
                at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@listPlugin.handle()
async def listPluginHandle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State, args: Message = CommandArg()):
    try:
        args = Command.formatToCommand(str(args).strip())[0]
        if args[0] == "":
            pluginList = getPluginDict().values()
            reply = "插件列表如下:\n\n"
            for plugin in pluginList:
                reply += "%s%s%s\n" % ("[内置]" if plugin.built_in else "", plugin.pluginName,
                                       "" if await getPluginEnable(event.message_type, ExtraData.getTargetId(event),
                                                                   plugin) else "[未启用]")
            reply += "\n# \"help <插件名>\"获取插件的帮助文档\n\n" \
                     "# \"help <插件名> <子文档>...\"获取插件的子文档\n\n" \
                     "# <>是必填，[]是可选，输入时无需带<>和[]\n\n" \
                     "# 更详细的使用手册：https://github.com/snowyfirefly/Liteyuki-Bot/blob/master/docs/usage_user.md"
            await listPlugin.send(message=reply)
        else:
            pluginName = args[0]
            plugin: Plugin = searchForPlugin(pluginName)

            if plugin is not None:
                if len(args) == 1:
                    await listPlugin.send(Message("%s帮助文档：\n\n" % plugin.pluginName + plugin.pluginDocs))
                else:
                    await listPlugin.send(Message("%s帮助文档：\n\n" % "-".join(args) + await plugin.get_sub_docs(args[1:], plugin_name=plugin.pluginName)))
            else:
                await listPlugin.send("未找到插件")

    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@createPlugin.handle()
async def createPluginHandle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(event.raw_message)
        pluginName = args[1]
        pluginId = args[2]
        if len(args) >= 4:
            pluginFolder = args[3]
        else:
            pluginFolder = args[2].replace(".", "_")
        pluginDir = os.path.join(ExConfig.plugins_path, pluginFolder)
        if os.path.exists(pluginDir):
            await createPlugin.send("创建失败, 文件夹名重复")
        else:
            os.mkdir(pluginDir)
            os.mkdir(os.path.join(pluginDir, "config"))
            open(os.path.join(pluginDir, "__init__.py"), "w", encoding="utf-8").close()
            with open(os.path.join(pluginDir, "config/manifest.json"), "w", encoding="utf-8") as file:
                json.dump({"name": pluginName, "id": pluginId}, file, indent=4, ensure_ascii=False)
            open(os.path.join(pluginDir, "config/docs.txt"), "w", encoding="utf-8").close()
            await createPlugin.send("插件 %s(%s) 创建成功" % (pluginName, pluginId))
    except BaseException as e:
        await Session.sendException(bot, event, state, e)
