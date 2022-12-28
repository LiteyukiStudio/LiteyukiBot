import json
import os
import time
import traceback
from typing import Union

from nonebot.params import CommandArg
from nonebot.utils import run_sync
from .utils import *
from ...liteyuki_api.config import *
from ...liteyuki_api.data import LiteyukiDB
from nonebot import *
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Message
from nonebot.permission import SUPERUSER

from ...liteyuki_api.utils import simple_request

check_update = on_command("检查更新", permission=SUPERUSER)
set_auto_update = on_command("启用自动更新", aliases={"停用自动更新"}, permission=SUPERUSER)
update = on_command("#update", aliases={"#轻雪更新"}, permission=SUPERUSER)
restart = on_command("#restart", aliases={"#轻雪重启"}, permission=SUPERUSER)
export_database = on_command("#export", aliases={"#导出数据"}, permission=SUPERUSER)


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
    check_url = "https://gitee.com/snowykami/liteyuki-bot/raw/master/src/config/config.json"
    local_version_id: int = config_data.get("version_id", None)
    local_version_name: str = config_data.get("version_name", None)
    resp = await run_sync(simple_request)(check_url)
    resp_data = resp.json()
    await update.send("开始更新:\n当前：%s(%s)\n更新：%s(%s)" % (local_version_name, local_version_id, resp_data.get("version_name"), resp_data.get("version_id")), at_sender=True)
    await run_sync(os.system)("git pull --force https://gitee.com/snowykami/liteyuki-bot.git")
    await update.send("更新完成，正在重启", at_sender=True)
    restart_bot()


@restart.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], arg: Message = CommandArg()):
    await restart.send("正在重启", at_sender=True)
    restart_bot()


@export_database.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    export_db = {"export_time": tuple(time.localtime())[0:6]}
    for collection_name in LiteyukiDB.list_collection_names():
        export_db[collection_name] = []
        for document in LiteyukiDB[collection_name].find():
            for k, v in document.items():
                print(type(k), type(v))
            export_db[collection_name].append(document)
    f_path = os.path.join(Path.cache, "liteyuki.json")

    def export():
        f = open(f_path, "w", encoding="utf-8")
        json.dump(export_db, f, indent=4, ensure_ascii=False)
        f.close()

    await run_sync(export)()
    datetime = "%s-%s-%s-%s-%s-%s" % tuple(time.localtime())[0:6]
    await bot.call_api("upload_private_file", user_id=event.user_id, file=f_path, name="liteyuki_%s.json" % datetime)
