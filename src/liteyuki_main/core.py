import base64
import time
from typing import Any, AnyStr

import nonebot
import pip
from nonebot import Bot, get_driver, require
from nonebot.adapters import onebot, satori
from nonebot.adapters.onebot.v11 import Message, unescape
from nonebot.exception import MockApiException
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER

# from src.liteyuki.core import Reloader
from src.utils import event as event_utils, satori_utils
from src.utils.base.config import get_config, load_from_yaml
from src.utils.base.data_manager import StoredConfig, TempConfig, common_db
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md, broadcast_to_superusers
from .api import update_liteyuki
from ..utils.base import reload
from ..utils.base.ly_function import get_function

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma, MultiVar
from nonebot_plugin_apscheduler import scheduler

driver = get_driver()

markdown_image = common_db.where_one(StoredConfig(), default=StoredConfig()).config.get("markdown_image", False)


@on_alconna(
    command=Alconna(
        "liteecho",
        Args["text", str, ""],
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(bot: T_Bot, matcher: Matcher, result: Arparma):
    if result.main_args.get("text"):
        await matcher.finish(Message(unescape(result.main_args.get("text"))))
    else:
        await matcher.finish(f"Hello, Liteyuki!\nBot {bot.self_id}")


@on_alconna(
    aliases={"更新轻雪"},
    command=Alconna(
        "update-liteyuki"
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(bot: T_Bot, event: T_MessageEvent):
    # 使用git pull更新

    ulang = get_user_lang(str(event.user.id if isinstance(event, satori.event.Event) else event.user_id))
    success, logs = update_liteyuki()
    reply = "Liteyuki updated!\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.btn_cmd(ulang.get("liteyuki.restart_now"), "reload-liteyuki")
    pip.main(["install", "-r", "requirements.txt"])
    reply += f"{ulang.get('liteyuki.update_restart', RESTART=btn_restart)}"
    await md.send_md(reply, bot, event=event, at_sender=False)


@on_alconna(
    aliases={"重启轻雪"},
    command=Alconna(
        "reload-liteyuki"
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(matcher: Matcher, bot: T_Bot, event: T_MessageEvent):
    await matcher.send("Liteyuki reloading")
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())

    temp_data.data.update(
        {
                "reload"             : True,
                "reload_time"        : time.time(),
                "reload_bot_id"      : bot.self_id,
                "reload_session_type": event_utils.get_message_type(event),
                "reload_session_id"  : (event.group_id if event.message_type == "group" else event.user_id)
                    if not isinstance(event, satori.event.Event) else event.chan_active.id,
                "delta_time"         : 0
        }
    )

    common_db.save(temp_data)
    reload()


@on_alconna(
    aliases={"配置"},
    command=Alconna(
        "config",
        Subcommand(
            "set",
            Args["key", str]["value", Any],
            alias=["设置"],

        ),
        Subcommand(
            "get",
            Args["key", str, None],
            alias=["查询", "获取"]
        ),
        Subcommand(
            "remove",
            Args["key", str],
            alias=["删除"]
        )
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot, matcher: Matcher):
    ulang = get_user_lang(str(event_utils.get_user_id(event)))
    stored_config: StoredConfig = common_db.where_one(StoredConfig(), default=StoredConfig())
    if result.subcommands.get("set"):
        key, value = result.subcommands.get("set").args.get("key"), result.subcommands.get("set").args.get("value")
        try:
            value = eval(value)
        except:
            pass
        stored_config.config[key] = value
        common_db.save(stored_config)
        await matcher.finish(f"{ulang.get('liteyuki.config_set_success', KEY=key, VAL=value)}")
    elif result.subcommands.get("get"):
        key = result.subcommands.get("get").args.get("key")
        file_config = load_from_yaml("config.yml")
        reply = f"{ulang.get('liteyuki.current_config')}"
        if key:
            reply += f"```dotenv\n{key}={file_config.get(key, stored_config.config.get(key))}\n```"
        else:
            reply = f"{ulang.get('liteyuki.current_config')}"
            reply += f"\n{ulang.get('liteyuki.static_config')}\n```dotenv"
            for k, v in file_config.items():
                reply += f"\n{k}={v}"
            reply += "\n```"
            if len(stored_config.config) > 0:
                reply += f"\n{ulang.get('liteyuki.stored_config')}\n```dotenv"
                for k, v in stored_config.config.items():
                    reply += f"\n{k}={v} {type(v)}"
                reply += "\n```"
        await md.send_md(reply, bot, event=event)
    elif result.subcommands.get("remove"):
        key = result.subcommands.get("remove").args.get("key")
        if key in stored_config.config:
            stored_config.config.pop(key)
            common_db.save(stored_config)
            await matcher.finish(f"{ulang.get('liteyuki.config_remove_success', KEY=key)}")
        else:
            await matcher.finish(f"{ulang.get('liteyuki.invalid_command', TEXT=key)}")


@on_alconna(
    aliases={"切换图片模式"},
    command=Alconna(
        "switch-image-mode"
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(event: T_MessageEvent, matcher: Matcher):
    global markdown_image
    # 切换图片模式，False以图片形式发送，True以markdown形式发送
    ulang = get_user_lang(str(event_utils.get_user_id(event)))
    stored_config: StoredConfig = common_db.where_one(StoredConfig(), default=StoredConfig())
    stored_config.config["markdown_image"] = not stored_config.config.get("markdown_image", False)
    markdown_image = stored_config.config["markdown_image"]
    common_db.save(stored_config)
    await matcher.finish(
        ulang.get("liteyuki.image_mode_on" if stored_config.config["markdown_image"] else "liteyuki.image_mode_off"))


@on_alconna(
    command=Alconna(
        "liteyuki-docs",
    ),
    aliases={"轻雪文档"},
).handle()
# Satori OK
async def _(matcher: Matcher):
    await matcher.finish("https://bot.liteyuki.icu/usage")


@on_alconna(
    command=Alconna(
        "/function",
        Args["function", str]["args", MultiVar(str), ()],
    ),
    permission=SUPERUSER
).handle()
async def _(result: Arparma, bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    """
    调用轻雪函数
    Args:
        result:
        bot:
        event:

    Returns:

    """
    function_name = result.main_args.get("function")
    args: tuple[str] = result.main_args.get("args", ())
    _args = []
    _kwargs = {
            "USER_ID" : str(event.user_id),
            "GROUP_ID": str(event.group_id) if event.message_type == "group" else "0",
            "BOT_ID"  : str(bot.self_id)
    }

    for arg in args:
        arg = arg.replace("\\=", "EQUAL_SIGN")
        if "=" in arg:
            key, value = arg.split("=", 1)
            value = unescape(value.replace("EQUAL_SIGN", "="))
            try:
                value = eval(value)
            except:
                value = value
            _kwargs[key] = value
        else:
            _args.append(arg.replace("EQUAL_SIGN", "="))

    ly_func = get_function(function_name)
    ly_func.bot = bot if "BOT_ID" not in _kwargs else nonebot.get_bot(_kwargs["BOT_ID"])
    ly_func.matcher = matcher

    await ly_func(*tuple(_args), **_kwargs)


@on_alconna(
    command=Alconna(
        "/api",
        Args["api", str]["args", MultiVar(AnyStr), ()],
    ),
    permission=SUPERUSER
).handle()
async def _(result: Arparma, bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    """
    调用API
    Args:
        result:
        bot:
        event:

    Returns:

    """
    api_name = result.main_args.get("api")
    args: tuple[str] = result.main_args.get("args", ())  # 类似于url参数，但每个参数间用空格分隔，空格是%20
    args_dict = {}

    for arg in args:
        key, value = arg.split("=", 1)

        args_dict[key] = unescape(value.replace("%20", " "))

    if api_name in need_user_id and "user_id" not in args_dict:
        args_dict["user_id"] = str(event.user_id)
    if api_name in need_group_id and "group_id" not in args_dict and event.message_type == "group":
        args_dict["group_id"] = str(event.group_id)

    if "message" in args_dict:
        args_dict["message"] = Message(eval(args_dict["message"]))

    if "messages" in args_dict:
        args_dict["messages"] = Message(eval(args_dict["messages"]))

    try:
        result = await bot.call_api(api_name, **args_dict)
    except Exception as e:
        result = str(e)

    args_show = "\n".join("- %s: %s" % (k, v) for k, v in args_dict.items())
    await matcher.finish(f"API: {api_name}\n\nArgs: \n{args_show}\n\nResult: {result}")


# system hook
@Bot.on_calling_api  # 图片模式检测
async def test_for_md_image(bot: T_Bot, api: str, data: dict):
    # 截获大图发送，转换为markdown发送
    if api in ["send_msg", "send_private_msg", "send_group_msg"] and markdown_image and data.get(
            "user_id") != bot.self_id:
        if api == "send_msg" and data.get("message_type") == "private" or api == "send_private_msg":
            session_type = "private"
            session_id = data.get("user_id")
        elif api == "send_msg" and data.get("message_type") == "group" or api == "send_group_msg":
            session_type = "group"
            session_id = data.get("group_id")
        else:
            return
        if len(data.get("message", [])) == 1 and data["message"][0].get("type") == "image":
            file: str = data["message"][0].data.get("file")
            # file:// http:// base64://
            if file.startswith("http"):
                result = await md.send_md(await md.image_async(file), bot, message_type=session_type,
                                          session_id=session_id)
            elif file.startswith("file"):
                file = file.replace("file://", "")
                result = await md.send_image(open(file, "rb").read(), bot, message_type=session_type,
                                             session_id=session_id)
            elif file.startswith("base64"):
                file_bytes = base64.b64decode(file.replace("base64://", ""))
                result = await md.send_image(file_bytes, bot, message_type=session_type, session_id=session_id)
            else:
                return
            raise MockApiException(result=result)


@driver.on_startup
async def on_startup():
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())
    # 储存重启信息
    if temp_data.data.get("reload", False):
        delta_time = time.time() - temp_data.data.get("reload_time", 0)
        temp_data.data["delta_time"] = delta_time
        common_db.save(temp_data)  # 更新数据
    """
    该部分将迁移至轻雪生命周期
    Returns:

    """


@driver.on_shutdown
async def on_shutdown():
    pass


@driver.on_bot_connect
async def _(bot: T_Bot):
    temp_data = common_db.where_one(TempConfig(), default=TempConfig())
    if isinstance(bot, satori.Bot):
        await satori_utils.user_infos.load_friends(bot)
    # 用于重启计时
    if temp_data.data.get("reload", False):
        temp_data.data["reload"] = False
        reload_bot_id = temp_data.data.get("reload_bot_id", 0)
        if reload_bot_id != bot.self_id:
            return
        reload_session_type = temp_data.data.get("reload_session_type", "private")
        reload_session_id = temp_data.data.get("reload_session_id", 0)
        delta_time = temp_data.data.get("delta_time", 0)
        common_db.save(temp_data)  # 更新数据

        if delta_time <= 20.0:  # 启动时间太长就别发了，丢人
            if isinstance(bot, satori.Bot):
                await bot.send_message(
                    channel_id=reload_session_id,
                    message="Liteyuki reloaded in %.2f s" % delta_time
                )
            elif isinstance(bot, onebot.v11.Bot):
                await bot.send_msg(
                    message_type=reload_session_type,
                    user_id=reload_session_id,
                    group_id=reload_session_id,
                    message="Liteyuki reloaded in %.2f s" % delta_time
                )

            elif isinstance(bot, onebot.v12.Bot):
                await bot.send_message(
                    message_type=reload_session_type,
                    user_id=reload_session_id,
                    group_id=reload_session_id,
                    message="Liteyuki reloaded in %.2f s" % delta_time,
                    detail_type="group"
                )


# 每天4点更新
@scheduler.scheduled_job("cron", hour=4)
async def every_day_update():
    if get_config("auto_update", default=True):
        result, logs = update_liteyuki()
        pip.main(["install", "-r", "requirements.txt"])
        if result:
            await broadcast_to_superusers(f"Liteyuki updated: ```\n{logs}\n```")
            nonebot.logger.info(f"Liteyuki updated: {logs}")
            reload()
        else:
            nonebot.logger.info(logs)


# 需要用户id的api
need_user_id = (
        "send_private_msg",
        "send_msg",
        "set_group_card",
        "set_group_special_title",
        "get_stranger_info",
        "get_group_member_info"
)

need_group_id = (
        "send_group_msg",
        "send_msg",
        "set_group_card",
        "set_group_name",

        "set_group_special_title",
        "get_group_member_info",
        "get_group_member_list",
        "get_group_honor_info"
)
