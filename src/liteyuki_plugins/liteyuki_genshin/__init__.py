import traceback
from datetime import time

from PIL import ImageEnhance
from nonebot import on_command, on_message
from nonebot.permission import SUPERUSER
from nonebot.plugin import PluginMetadata

from .user_card import *
from .character_card import *
from .utils import *
from .resource import *

set_uid = on_command(cmd="绑定uid", aliases={"#绑定uid", "绑定UID", "#绑定UID"}, block=True)
hid_uid = on_command(cmd="遮挡uid", block=True)
update_resource = on_command(cmd="原神资源更新", block=True, permission=SUPERUSER)
add_aliases = on_command(cmd="添加别称", block=True, permission=SUPERUSER)


@set_uid.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    args, kwargs = Command.formatToCommand(str(args).strip())
    if not args[0].isdigit():
        await set_uid.finish("uid格式错误", at_sender=True)
    else:
        uid = int(args[0])
        async with aiohttp.request("GET", url="https://enka.microgg.cn/u/%s" % uid) as resp:
            player_data = await resp.json()

            if len(player_data) == 0:
                await set_uid.finish("uid信息不存在", at_sender=True)
            else:
                playerInfo = player_data["playerInfo"]
                lang = kwargs.get("lang", "zh-CN")

                Data(Data.users, event.user_id).set_data(key="genshin.uid", value=uid)
                Data(Data.users, event.user_id).set_data(key="genshin.lang", value=lang)
                await set_uid.finish("绑定成功：%s（%s  Lv.%s）" % (playerInfo["nickname"], servers.get(str(uid)[0], "Unknown Server"), playerInfo["level"]), at_sender=True)
                if len(player_data.get("avatarInfoList", [])) > 0:
                    player_data["time"] = tuple(list(time.localtime())[0:5])
                    Data(Data.globals, "genshin_player_data").set_data(str(uid), player_data)


@hid_uid.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    raw_stats = Data(Data.users, event.user_id).get_data(key="genshin.hid_uid", default=False)
    Data(Data.users, event.user_id).set_data(key="genshin.hid_uid", value=not raw_stats)
    await hid_uid.finish("已%suid遮挡" % ("关闭" if raw_stats else "开启"), at_sender=True)


@update_resource.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    for res_file in resource.items():
        if not os.path.exists(os.path.join(Path.root, res_file[0])):
            print("正在下载：%s" % res_file[0])
            await run_sync(download_file)(res_file[1], os.path.join(Path.root, res_file[0]))
    if not os.path.exists(os.path.join(Path.data, "genshin")):
        os.makedirs(os.path.join(Path.data, "genshin"))
    for file, url in resource_pool.items():
        await update_resource.send("正在更新：%s" % file)
        await run_sync(download_file)(url, os.path.join(Path.data, "genshin", file))
    await update_resource.finish("资源更新完成", at_sender=True)


@add_aliases.handle()
async def _(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent], args: Message = CommandArg()):
    file_pool = {}
    for f in resource_pool.keys():
        if os.path.exists(os.path.join(Path.data, "genshin", f)):
            file_pool[f] = json.load(open(os.path.join(Path.data, "genshin", f), encoding="utf-8"))
        else:
            await user_card.finish("数据缺失，请先发送“原神资源更新”以更新基础资源库")
    args, kwargs = Command.formatToCommand(cmd=str(args))
    identify_name = args[0]
    if len(args) > 1:
        _break = False
        aliases = args[1:]
        hash_id = str()
        for lang, lang_data in file_pool["loc.json"].items():
            for hash_id, entry in lang_data.items():
                if identify_name == entry:
                    _break = True
                    break
            if _break:
                break
        else:
            await add_aliases.finish(data_lost, at_sender=True)
        character_hash_id = hash_id

        character_id = 0
        character = {}
        for character_id, character in file_pool["characters_enka.json"].items():
            if int(hash_id) == character["NameTextMapHash"]:
                character_id = character_id
                break
        else:
            await add_aliases.finish(data_lost, at_sender=True)

        data = Data(Data.globals, "genshin_game_data").get_data(key="character_aliases", default={})
        if hash_id in data:
            data[hash_id] += aliases
        else:
            data[hash_id] = aliases
        data[hash_id] = list(set(data[hash_id]))
        Data(Data.globals, "genshin_game_data").set_data(key="character_aliases", value=data)
        await add_aliases.finish("别称添加完成：%s(%s)：%s" % (identify_name, hash_id, aliases))

    else:
        await add_aliases.finish("请至少添加一个别称", at_sender=True)


__plugin_meta__ = PluginMetadata(
    name="原神查询",
    description="原神角色面板查询",
    usage="命令：\n"
          "•「原神资源更新」更新本地的资源文件\n"
          "•「xx面板」查看角色面板\n"
          "•「xx角色数据]获取角色原始数据文件\n"
          "•「原神数据 [uid]」更新原神角色展示框中的数据,默认为绑定的uid\n"
          "•「绑定uid 000000000」绑定自己的uid\n"
          "•「添加别称 角色名 别称1 别称2...」在查询面板时可以用别称查询\n"
          "•可以在「绑定uid」空格后接「lang=xx」来指定语言，可选的语言有：\n"
          "en ru vi th pt ko ja id fr es de zh-TW zh-CN it tr\n"
          "•可在「xxx面板」、「xx角色数据]空格后接「hd=true」来生成高清面板\n"
          "•可在「xxx面板」、「xx角色数据]空格后接「uid=000000000」来指定uid\n",
    extra={
        "default_enable": True,
        "liteyuki_resource": resource,
        "liteyuki_plugin": True
    }
)
