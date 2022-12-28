import os
import traceback
from typing import Union

from nonebot.params import CommandArg
from nonebot.utils import run_sync
from .utils import *
from ...liteyuki_api.config import *
from nonebot import *
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Message
from nonebot.permission import SUPERUSER

from ...liteyuki_api.utils import simple_request

check_update = on_command("检查更新", permission=SUPERUSER)
set_auto_update = on_command("启用自动更新", aliases={"停用自动更新"}, permission=SUPERUSER)
update = on_command("#update", permission=SUPERUSER)
restart = on_command("#restart", permission=SUPERUSER)
install_plugin = on_command("#install", permission=SUPERUSER)
uninstall_plugin = on_command("#uninstall", permission=SUPERUSER)


@check_update.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    check_url = "https://gitee.com/snowykami/liteyuki-bot/raw/master/src/config/config.json"
    local_version_id: int = config_data.get("version_id", None)
    local_version_name: str = config_data.get("version_name", None)
    resp = await run_sync(simple_request)(check_url)
    resp_data = resp.json()
    msg = "当前版本：%s(%s)\n仓库版本：%s(%s)" % (local_version_name, local_version_id, resp_data.get("version_name"), resp_data.get("version_id"))
    if resp_data.get("version_id") > local_version_id:
        msg += "\n检测到新版本：\n请使用「#update BotQQ号」命令手动更新"
    await check_update.send(msg)


@update.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    if str(arg).strip() == str(bot.self_id):
        check_url = "https://gitee.com/snowykami/liteyuki-bot/raw/master/src/config/config.json"
        local_version_id: int = config_data.get("version_id", None)
        local_version_name: str = config_data.get("version_name", None)
        resp = await run_sync(simple_request)(check_url)
        resp_data = resp.json()
        await update.send("开始更新:\n当前：%s(%s)\n更新：%s(%s)" % (local_version_name, local_version_id, resp_data.get("version_name"), resp_data.get("version_id")), at_sender=True)
        await run_sync(os.system)("git pull --force https://gitee.com/snowykami/liteyuki-bot.git")
        await update.send("更新完成，正在重启", at_sender=True)
        restart_bot()
    else:
        await update.send("账号验证失败，无法更新", at_sender=True)


@restart.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    await restart.send("正在重启", at_sender=True)
    restart_bot()


@install_plugin.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    args = str(arg).strip().split()
    for plugin_name in args:
        try:
            await install_plugin.send("正在尝试安装%s" % plugin_name)
            result = await run_sync(os.popen)("nb plugin install %s" % plugin_name)
            if "Successfully installed" in result.splitlines()[-1]:
                await install_plugin.send("%s安装成功" % plugin_name)
            else:
                await install_plugin.send("插件安装失败:%s" % result)
        except BaseException as e:
            await install_plugin.send("安装%s出现错误:%s" % (plugin_name, traceback.format_exc(e)))
