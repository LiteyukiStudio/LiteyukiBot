import sys

import asyncio
import random
from nonebot import require
import aiohttp
import threading
from nonebot import on_command
from nonebot.adapters.onebot.v11 import GROUP_OWNER, GROUP_ADMIN, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ...extraApi.permission import MASTER
from .stApi import *
import os

# require("nonebot_plugin_reboot")
from ...extraApi.reload import Reloader

#    ahhaha
setConfig = on_command(cmd="设置数据", permission=SUPERUSER | MASTER, priority=1, block=True)
getConfig = on_command(cmd="获取数据", permission=SUPERUSER | MASTER, priority=1, block=True)
send_mutil_msg = on_command(cmd="群发消息", permission=SUPERUSER | MASTER, priority=1, block=True)
backup_data = on_command(cmd="备份数据", permission=SUPERUSER | MASTER, priority=1, block=True)
statistics_data = on_command(cmd='统计数据', permission=SUPERUSER | MASTER, priority=1, block=True)
enable_group = on_command(cmd="群聊启用", permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN, priority=1, block=True)
disable_group = on_command(cmd="群聊停用", permission=SUPERUSER | GROUP_OWNER | GROUP_ADMIN, priority=1, block=True)
clear_cache = on_command(cmd="清除缓存", permission=SUPERUSER, block=True)
call_api = on_command(cmd="/api", permission=SUPERUSER | MASTER, priority=1, block=True)
update = on_command(cmd="/update", permission=SUPERUSER | MASTER, priority=1, block=True)
install_plugin = on_command(cmd="安装插件", permission=SUPERUSER, priority=1, block=True)
reload = on_command("/reload", aliases={"/reboot"}, permission=SUPERUSER, priority=1, block=True)
cmd = on_command("/cmd", permission=SUPERUSER, priority=1, block=True)
config = on_command("/config", permission=SUPERUSER, priority=1, block=True)
env = on_command("/env", permission=SUPERUSER, priority=1, block=True)


@enable_group.handle()
async def enable_group_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State, args: Message = CommandArg()):
    if str(args).strip() == "":
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id
        else:
            await enable_group.finish("命令参数缺失：群号")
            group_id = 0
    else:
        group_id = int(str(args).strip())
    state2 = await ExtraData.get_group_data(group_id=group_id, key="enable", default=False)
    group_info = await bot.get_group_info(group_id=group_id)
    if state2:
        await enable_group.send(message="群：%s已启用机器人，无需再次操作" % group_info["group_name"])
    else:

        await ExtraData.set_group_data(group_id=group_id, key="enable", value=True)
        await enable_group.send(message="群聊启用成功：%s" % group_info["group_name"])


@disable_group.handle()
async def enable_group_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    if len(event.raw_message.split()) == 2:
        group_id = int(event.raw_message.split()[1])
    elif type(event) is GroupMessageEvent:
        group_id = event.group_id
    else:
        group_id = 0
    state2 = await ExtraData.get_group_data(group_id=group_id, key="enable", default=False)
    if not state2:
        await disable_group.send(message="该群已停用机器人，无需再次操作")
    else:
        await ExtraData.set_group_data(group_id=group_id, key="enable", value=False)
        await enable_group.send(message="群聊停用成功")


@setConfig.handle()
async def setConfigHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(Command.escape(event.raw_message))

        targetType = args[1]
        targetId = args[2]
        key = args[3]
        value = eval(Command.formatToString(*args[4:]))
        if targetType == "gm":
            r = await ExtraData.set_group_member_data(event.group_id, targetId, key=key, value=value)
            if r:
                await setConfig.send("属性设置成功:\n%s%s\n%s:%s" % (targetType, targetId, key, value))
            else:
                await setConfig.send("属性设置失败")
        else:
            r = await ExtraData.setData(targetType=targetType, targetId=targetId, key=key, value=value)
            if r:
                await setConfig.send("属性设置成功:\n%s%s\n%s:%s" % (targetType, targetId, key, value))
            else:
                await setConfig.send("属性设置失败")
    except BaseException as e:
        await Session.sendException(bot, event, state, e, text="请检查字符串是否用单双引号括起来了，括号是否成对输入，特殊字符是否转义")


@getConfig.handle()
async def getConfigHandle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent, state: T_State):
    try:
        args, kws = Command.formatToCommand(event.raw_message)
        targetType = args[1]
        targetId = int(args[2])
        key = args[3]

        if targetType in ["g", "gm"] and await(GROUP_OWNER | GROUP_ADMIN | SUPERUSER)(bot, event) or await SUPERUSER(bot, event):
            if targetType == "gm":
                r = await ExtraData.get_group_member_data(event.group_id, targetId, key=key)
            else:
                r = await ExtraData.getData(targetType=targetType, targetId=targetId, key=key)
            args = list(args)
            args.append(r)
            args.append(type(r))
            await getConfig.send("- 类: %s\n- 值: %s" % (type(r), r))
        else:
            await getConfig.send("你没有权限查看此条目", at_sender=True)
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@send_mutil_msg.handle()
async def send_mutil_msg_handle(bot: Bot, event: PrivateMessageEvent, state: T_State):
    friend_list = await bot.get_friend_list()
    args = event.raw_message.split()
    msg = Message(" ".join(args[1:]))
    for friend in friend_list:
        try:
            friend_info = await bot.get_stranger_info(user_id=friend["user_id"])
            if await ExtraData.get_user_data(user_id=friend["user_id"], key="enable", default=False):
                await bot.send_private_msg(user_id=friend["user_id"], message=msg)
                await send_mutil_msg.send(message="消息已发送到：%s(%s)" % (friend_info["nickname"], friend["user_id"]))
        except BaseException as e:
            await Session.sendException(bot, event, state, e)

        await asyncio.sleep(random.randint(15, 30))


@backup_data.handle()
async def backup_data_handle(bot: Bot, event: GroupMessageEvent | PrivateMessageEvent):
    f, n = await backup()
    await backup_data.send(message="数据备份完成：%s，共计%s个数据库" % (f, n))


@call_api.handle()
async def call_api_handle(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], state: T_State):
    try:
        args, kws = Command.formatToCommand(cmd=Command.escape(event.raw_message))
        r = await bot.call_api(args[1], **kws)
        await call_api.send(message=str(r))
    except BaseException as e:
        await Session.sendException(bot, event, state, e)


@install_plugin.handle()
async def install_plugin_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State, args: Message = CommandArg()):
    @run_sync
    def _install(_plugin_name: str):
        result = os.system("nb plugin install %s" % _plugin_name)
        return result

    plugin_list = str(args).split(",")
    try:
        for plugin in plugin_list:
            r = await _install(plugin)
            await install_plugin.send("插件:%s安装成功" % plugin)

        # await install_plugin.send("正在重载中...")
        # threading.Thread(target=os.system, args=("python %s" % os.path.join(os.path.dirname(__file__), "restart.py"),)).start()
        # await asyncio.sleep(2)
        Reloader.reload()

    except BaseException as e:
        await Session.sendException(bot, event, state, e, "插件安装失败")


@update.handle()
async def update_handle(bot: Bot, event: Union[PrivateMessageEvent, GroupMessageEvent], state: T_State):
    try:
        args, kwargs = Command.formatToCommand(event.raw_message)

        # 获取本地版本数据
        async with aiofiles.open(os.path.join(ExConfig.res_path, "version.json"), "r", encoding="utf-8") as file:
            file_data = json.loads(await file.read())
            now_version = file_data.get("version", "0.0.0")
            now_version_description = file_data.get("description", "无")

        version_check_list = [
            "https://raw.fastgit.org/snowyfirefly/Liteyuki-Bot/master/resource/version.json",
            "https://cdn.githubjs.cf/snowyfirefly/Liteyuki-Bot/raw/master/resource/version.json",
            "https://raw.xn--gzu630h.xn--kpry57d/snowyfirefly/Liteyuki-Bot/master/resource/version.json",
            "https://gitee.com/snowykami/Liteyuki/raw/master/resource/version.json",
        ]

        # 获取新版本数据
        for version_url in version_check_list:
            try:
                async with aiohttp.request("GET", url=version_url) as resp:
                    online_version_data = json.loads(await resp.text())
                    online_version = online_version_data.get("version")
                    print(online_version)
                break
            except BaseException as e:
                online_version = "检查失败"
                continue

        if now_version != online_version or kwargs.get("mode") == "force":

            if kwargs.get("mode") == "check":
                if online_version != now_version:
                    await update.send("检测到更新：\n - 当前版本：%s\n - 新版本：%s" % (now_version, online_version))
                else:
                    await update.send("当前已是最新版本：%s(%s)" % (now_version, now_version_description))

            else:
                source_list: list = online_version_data.get("download", [
                    "https://github.com/snowyfirefly/Liteyuki-Bot/archive/refs/heads/master.zip",
                    "https://hub.fastgit.xyz/snowyfirefly/Liteyuki-Bot/archive/refs/heads/master.zip"])

                if "url" in kwargs:
                    source_list.insert(0, kwargs["url"])

                for i, url in enumerate(source_list):
                    try:
                        await update.send("%s下载更新：\n%s -> %s\n源：%s" % ("开始" if i == 0 else "当前源不可用，正在从其他源重试", now_version, online_version, url))
                        r = await ExtraData.download_file(url, os.path.join(ExConfig.cache_path, "version/new_code.zip"))
                        if r:
                            break
                    except BaseException:
                        continue
                else:
                    r = False
                if r:
                    await update.send("下载完成，正在安装")
                    await update_move()
                    await update.send("更新安装完成，正在重启")
                    Reloader.reload()
                else:
                    await update.send("下载更新失败，请检查网络")
        else:
            await update.send("当前已是最新版本：%s(%s)" % (now_version, now_version_description))

    except BaseException as e:
        await Session.sendException(bot, event, state, e, "检查更新失败")


@reload.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    await reload.send("正在重启...")
    Reloader.reload()


@cmd.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    cmd_str = Command.escape(str(args)).strip()

    @run_sync
    def run_cmd(command: str):
        return os.popen(command).read()

    result = await run_cmd(cmd_str)
    print(result)

    await cmd.send("执行结果：\n%s" % result)


@config.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    try:
        args = Command.escape(str(args)).strip().split()
        if len(args) >= 1:
            config_name = args[0]
            if len(args) >= 2:
                config_value = eval(" ".join(args[1:]))
                await ExtraData.set_global_data(key=config_name, value=config_value)
                await config.send(message="属性设置成功：\n%s: %s" % (config_name, config_value))
            else:
                config_value = await ExtraData.get_global_data(key=config_name, default=None)
                await config.send(message="属性值：\n%s: %s" % (config_name, config_value))
    except BaseException as e:
        await Session.sendException(bot, event, {}, e)


@env.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    try:
        args = Command.escape(str(args)).strip().split()
        if len(args) >= 1:
            config_name = args[0]
            if len(args) >= 2:
                config_value = " ".join(args[1:])
                data = await Util.load_env(".env")
                data[config_name] = config_value
                await Util.dump_env(".env", data)
                await config.send(message="env属性设置成功：\n%s: %s\n正在重载中..." % (config_name, config_value))
                print(config_value, type(config_value))
                Reloader.reload()
            else:
                data = await Util.load_env(".env")
                config_value = data.get(config_name, "属性值不存在")
                await config.send(message="env属性值：\n%s: %s" % (config_name, config_value))
    except BaseException as e:
        await Session.sendException(bot, event, {}, e)


@clear_cache.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    if os.path.exists(ExConfig.cache_path) and len(os.listdir(ExConfig.cache_path)) > 0:
        print(os.path.getsize(ExConfig.cache_path))
        size = await run_sync(Util.size_text)(os.path.getsize(ExConfig.cache_path))
        await run_sync(shutil.rmtree)(ExConfig.cache_path)
        await run_sync(os.makedirs)(ExConfig.cache_path)
        await clear_cache.send(message="缓存清除成功：%s" % size)
    else:
        if not os.path.exists(ExConfig.cache_path):
            os.makedirs(ExConfig.cache_path)
        await clear_cache.send(message="当前没有缓存")
