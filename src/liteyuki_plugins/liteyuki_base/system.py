import json
import os
import time
import traceback
from typing import Union

from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot.utils import run_sync
from .utils import *
from ...liteyuki_api.config import *
from ...liteyuki_api.data import LiteyukiDB
from ...liteyuki_api.utils import *
from nonebot import *
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, Message, NoticeEvent, Bot
from nonebot.permission import SUPERUSER
import pickle
from ...liteyuki_api.utils import simple_request

check_update = on_command("检查更新", permission=SUPERUSER)
set_auto_update = on_command("启用自动更新", aliases={"停用自动更新"}, permission=SUPERUSER)
update = on_command("#update", aliases={"#轻雪更新"}, permission=SUPERUSER)
restart = on_command("#restart", aliases={"#轻雪重启"}, permission=SUPERUSER)
export_database = on_command("#export", aliases={"#导出数据"}, permission=SUPERUSER)
liteyuki_bot_info = on_command("#info", aliases={"#轻雪信息", "#轻雪状态"}, permission=SUPERUSER)

data_importer = on_notice()


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
            export_db[collection_name].append(document)
    f_path = os.path.join(Path.cache, "liteyuki.db")

    def export():
        f = open(f_path, "wb")
        pickle.dump(export_db, f)
        f.close()

    await run_sync(export)()
    datetime = "%s-%s-%s-%s-%s-%s" % tuple(time.localtime())[0:6]
    await bot.call_api("upload_private_file", user_id=event.user_id, file=f_path, name="liteyuki_%s.db" % datetime)


@data_importer.handle()
async def _(bot: Bot, event: NoticeEvent, state: T_State):
    eventData = event.dict()
    if str(eventData.get("user_id", None)) in bot.config.superusers:
        if event.notice_type == "offline_file":
            file = eventData["file"]
            name: str = file.get("name", "")
            if name.startswith("liteyuki") and name.endswith(".db"):
                url = file.get("url", "")
                path = os.path.join(Path.cache, name)
                await run_sync(download_file)(url, path)
                liteyuki_db = pickle.load(open(path, "rb"))
                for collection_name, collection_data in liteyuki_db.items():
                    collection = LiteyukiDB[collection_name]
                    if collection_name == "export_time":
                        continue
                    for document in collection_data:
                        for key, value in document.items():
                            collection.update_one(filter={"_id": document.get("_id")}, update={"$set": {key: value}}, upsert=True)
                await bot.send_private_msg(user_id=eventData.get("user_id"), message="数据库合并完成")


@liteyuki_bot_info.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    msg = "轻雪状态："
    stats = await bot.call_api("get_status")
    print(json.dumps(stats, indent=4))
    prop = {
        "Bot昵称": "、".join(bot.config.nickname if len(bot.config.nickname) else ["Bot还没有名字哦"]),
        "状态": "在线" if stats.get("online") else "离线",
        "群聊数": len(await bot.get_group_list()),
        "好友数": len(await bot.get_friend_list()),
        "收/发消息数": "%s/%s" % (stats.get("stat").get("message_received"), stats.get("stat").get("message_sent")),
        "收/发数据包数": "%s/%s" % (stats.get("stat").get("packet_received"), stats.get("stat").get("packet_sent"))
    }
    for prop_name, prop_value in prop.items():
        msg += "\n%s: %s" % (prop_name, prop_value)
    await liteyuki_bot_info.send(msg)
