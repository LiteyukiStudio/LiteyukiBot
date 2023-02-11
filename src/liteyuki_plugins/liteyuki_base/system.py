import datetime
import pickle
import platform
import random
import re
import shutil
import time

import psutil
from nonebot import *
from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent, NoticeEvent, MessageSegment, MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.utils import run_sync

from .state_card import generate_state_card
from .utils import *
from ...liteyuki_api.canvas import *
from ...liteyuki_api.config import *
from ...liteyuki_api.data import LiteyukiDB, Data
from ...liteyuki_api.update import update_liteyuki, update_resource
from ...liteyuki_api.utils import *

liteyuki_bot_info = on_command("#状态", aliases={"#state"})

check_update = on_command("#检查更新", aliases={"#check-update"}, permission=SUPERUSER)
update = on_command("#更新", aliases={"#update", "#更新资源", "#update-resource"}, permission=SUPERUSER)

restart = on_command("#重启", aliases={"#reboot"}, permission=SUPERUSER)

export_database = on_command("#导出数据", aliases={"#export-data"}, permission=SUPERUSER)

clear_cache = on_command("#清除缓存", aliases={"clear-cache"}, permission=SUPERUSER)

ban_user = on_command("#屏蔽用户", aliases={"#取消屏蔽", "#ban-user", "#unban-user"}, permission=SUPERUSER)
ban_group = on_command("#群聊启用", aliases={"#群聊停用", "#group-enable", "#group-disable"}, permission=SUPERUSER)

call_api = on_command("#api", permission=SUPERUSER)

set_bot_language = on_command("#设置默认语言", aliases={"#set-default-language"}, permission=SUPERUSER)
set_user_language = on_command("#设置语言", aliases={"#设置用户语言", "#set-language"})

data_importer = on_notice()


@check_update.handle()
async def _(event: MessageEvent):
    local_version_name, local_version_id, local_resource_id = get_local_version()
    online_version_name, online_version_id, online_resource_id = get_depository_version()
    msg = f"{await get_text_by_language('10000001', event.user_id)}: {local_version_name}.{local_version_id}\n" \
          f"{await get_text_by_language('10000002', event.user_id)}: {online_version_name}.{online_version_id}\n\n" \
          f"{await get_text_by_language('10000003', event.user_id)}: {local_version_name}.{local_resource_id}\n" \
          f"{await get_text_by_language('10000004', event.user_id)}: {online_version_name}.{online_resource_id}"
    if online_version_id > local_version_id:
        msg += await get_text_by_language("10000005", event.user_id)
    elif online_resource_id > local_resource_id:
        msg += await get_text_by_language("10000006", event.user_id)
    await check_update.send(msg)


@update.handle()
async def _(event: PrivateMessageEvent):
    local_version_name, local_version_id, local_resource_id = get_local_version()
    online_version_name, online_version_id, online_resource_id = get_depository_version()
    only_resource = False
    if re.search("(#更新资源)|(#update-resource)", event.raw_message) is not None:
        only_resource = True
    if not only_resource:
        await update.send(
            (await get_text_by_language("10000007", event.user_id)).format(local_version_name=local_version_name,
                                                                           online_version_name=online_version_name,
                                                                           local_version_id=local_version_id,
                                                                           online_version_id=online_version_id))
        await run_sync(update_liteyuki)()
    await update.send((await get_text_by_language("10000008", event.user_id)).format(
        local_version_name=local_version_name,
        online_version_name=online_version_name,
        local_resource_id=local_resource_id,
        online_resource_id=online_resource_id))
    await run_sync(update_resource)()
    if not only_resource:
        await update.send(await get_text_by_language("10000009", event.user_id), at_sender=True)
    restart_bot()


@restart.handle()
async def _(event: MessageEvent):
    await restart.send(await get_text_by_language("10000010", event.user_id), at_sender=True)
    restart_bot()


@export_database.handle()
async def _(bot: Bot, event: PrivateMessageEvent):
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
    _datetime = "-".join([str(i) for i in list(time.localtime())[0:6]])
    await bot.call_api("upload_private_file", user_id=event.user_id, file=f_path, name=f"liteyuki_{_datetime}.db")


# 轻雪状态
@liteyuki_bot_info.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    await generate_state_card(liteyuki_bot_info, bot, event)


# 清除缓存
@clear_cache.handle()
async def _(event: MessageEvent):
    file_list = []

    def get_all_file(_dir: str):
        for _f in os.listdir(_dir):
            wp = os.path.join(_dir, _f)
            if os.path.isdir(wp):
                get_all_file(wp)
            else:
                file_list.append(wp)

    get_all_file(Path.cache)

    if len(file_list) > 0:
        size_int = 0
        for f in file_list:
            size_int += os.path.getsize(f)
        size = size_text(size_int)
        await run_sync(shutil.rmtree)(Path.cache)
        await run_sync(os.makedirs)(Path.cache)
        await clear_cache.send(message=(await get_text_by_language("10000011", event.user_id)).format(size=size))
    else:
        if not os.path.exists(Path.cache):
            os.makedirs(Path.cache)
        await clear_cache.send(message=(await get_text_by_language("10000012", event.user_id)))


@call_api.handle()
async def _(bot: Bot, event: MessageEvent, arg: Message = CommandArg()):
    try:
        args, kwargs = Command.formatToCommand(str(arg), exe=True)
        result = await bot.call_api(args[0], **kwargs)
        await call_api.send(str(result))
    except BaseException as e:
        await call_api.send((await get_text_by_language("10000015", event.user_id)).format(error_text = traceback.format_exception(e)))
        traceback.print_exc()


@ban_user.handle()
async def _(event: MessageEvent, bot: Bot, arg: Message = CommandArg()):
    user_id_list = [int(i) for i in str(arg).strip().split()]
    banned_user_list = await Data(Data.globals, "liteyuki").get("banned_users", [])
    failed_list = []
    suc_list = []
    if re.search("(#屏蔽用户)|(#ban-user)", event.raw_message) is not None:
        ban = True
    else:
        ban = False
    info_dict = {}
    for ban_user_id in user_id_list:
        user_info = await bot.get_stranger_info(user_id=ban_user_id, no_cache=True)
        nickname = user_info["nickname"]
        info_dict[ban_user_id] = nickname
        if ban:
            if ban_user_id not in banned_user_list:
                banned_user_list.append(ban_user_id)
                suc_list.append(ban_user_id)
            else:
                failed_list.append(ban_user_id)
        else:
            if ban_user_id in banned_user_list:
                banned_user_list.remove(ban_user_id)
                suc_list.append(ban_user_id)
            else:
                failed_list.append(ban_user_id)

    msg = ""
    if len(suc_list) > 0:
        if ban:
            msg += await get_text_by_language("10000020", event.user_id)
        else:
            msg += await get_text_by_language("10000021", event.user_id)
        for suc_id in suc_list:
            msg += f"\n- {info_dict[suc_id]}({suc_id})"

    if len(failed_list) > 0:
        if len(suc_list) > 0:
            msg += "\n\n"
        if ban:
            msg += await get_text_by_language("10000022", event.user_id)
        else:
            msg += await get_text_by_language("10000023", event.user_id)
        for failed_id in failed_list:
            msg += f"\n- {info_dict[failed_id]}({failed_id})"
    if len(user_id_list) > 0:
        await Data(Data.globals, "liteyuki").set("banned_users", banned_user_list)
        await ban_user.send(msg)


@ban_group.handle()
async def __(event: Union[GroupMessageEvent, PrivateMessageEvent], bot: Bot, arg: Message = CommandArg()):
    if str(arg).strip().isdigit():
        group_id = int(str(arg).strip())
    else:
        group_id = event.group_id
    if re.search("(#群聊启用)|(#group-enable)", event.raw_message) is not None:
        enable = True
        state_text = await get_text_by_language("10000030", event.user_id)
    else:
        enable = False
        state_text = await get_text_by_language("10000031", event.user_id)
    group_data = await bot.get_group_info(group_id=group_id)
    if group_data is None:
        await ban_group.finish(await get_text_by_language("10000034", event.user_id))
    group_db = Data(Data.groups, group_id)
    group_state = await group_db.get("enable", True)
    if group_state == enable:
        await ban_group.finish((await get_text_by_language("10000032", event.user_id)).format(GROUP_NAME=group_data["group_name"],
                                                                                              GROUP_ID=group_id,
                                                                                              STATE=state_text))
    else:
        await group_db.set("enable", enable)
        await ban_group.finish((await get_text_by_language("10000033", event.user_id)).format(GROUP_NAME=group_data["group_name"],
                                                                                              GROUP_ID=group_id,
                                                                                              STATE=state_text))


@data_importer.handle()
async def _(bot: Bot, event: NoticeEvent):
    eventData = event.dict()
    if str(eventData.get("user_id", None)) in bot.config.superusers:
        # 超级用户判断
        if event.notice_type == "offline_file":
            # 判断为文件
            file = eventData["file"]
            name: str = file.get("name", "")
            if name.startswith("liteyuki") and name.endswith(".db"):
                # 导数据
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
                await bot.send_private_msg(user_id=eventData.get("user_id"), message=await get_text_by_language("10000040", eventData.get("user_id")))
            else:
                # 存文件
                url = file.get("url", "")
                path = os.path.join(Path.data, "file_receive", name)
                await run_sync(download_file)(url, path)
                await bot.send_private_msg(user_id=eventData.get("user_id"), message=(await get_text_by_language("10000041", eventData.get("user_id"))).format(PATH=path))


def get_lang_by_search(kw: str) -> str | None:
    for lang_name, lang_data in text_language_map.items():
        if kw == lang_name or kw == lang_data["name"]:
            print(lang_name)
            return lang_name


def get_supported_lang() -> str:
    return "\n- " + "\n- ".join([f'{lang_data["name"]}({lang_name})' for lang_name, lang_data in text_language_map.items()])


@set_bot_language.handle()
async def _(event: MessageEvent, arg: Message = CommandArg(), ):
    lang = get_lang_by_search(str(arg).strip())
    if lang is not None:
        await Data(Data.globals, "liteyuki").set("language", lang)
        await set_bot_language.send((await get_text_by_language("3", event.user_id)).format(LANG_NAME=(await get_text_by_language("name", lang))))
    else:
        reply = f'{await get_text_by_language("5", event.user_id)}\n{(await get_text_by_language("6", event.user_id)).format(LANG_LIST=get_supported_lang())}'
        await set_bot_language.send(reply)


@set_user_language.handle()
async def _(event: MessageEvent, arg: Message = CommandArg()):
    lang = get_lang_by_search(str(arg).strip())
    if lang is not None:
        await Data(Data.users, event.user_id).set("language", lang)
        await set_user_language.send((await get_text_by_language("4", event.user_id)).format(LANG_NAME=await get_text_by_language("name", lang)))
    else:
        reply = f'{await get_text_by_language("5", event.user_id)}\n{(await get_text_by_language("6", event.user_id)).format(LANG_LIST=get_supported_lang())}'
        await set_user_language.send(reply)
