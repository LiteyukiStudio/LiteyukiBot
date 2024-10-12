import time
from typing import AnyStr

import time
from typing import AnyStr

import nonebot
import pip
from nonebot import get_driver, require
from nonebot.adapters import onebot, satori
from nonebot.adapters.onebot.v11 import Message, unescape
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER

# from src.liteyuki.core import Reloader
from src.utils import event as event_utils, satori_utils
from src.utils.base.config import get_config
from src.utils.base.data_manager import TempConfig, common_db
from src.utils.base.language import get_user_lang
from src.utils.base.ly_typing import T_Bot, T_MessageEvent
from src.utils.message.message import MarkdownMessage as md, broadcast_to_superusers
from .api import update_liteyuki  # type: ignore
from src.utils.base import reload  # type: ignore
from src.utils.base.ly_function import get_function  # type: ignore
from src.utils.message.html_tool import md_to_pic

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna import UniMessage, on_alconna, Alconna, Args, Arparma, MultiVar
from nonebot_plugin_apscheduler import scheduler


driver = get_driver()


@on_alconna(
    command=Alconna(
        "liteecho",
        Args["text", str, ""],
    ),
    permission=SUPERUSER
).handle()
# Satori OK
async def _(bot: T_Bot, matcher: Matcher, result: Arparma):
    if text := result.main_args.get("text"):
        await matcher.finish(Message(unescape(text)))
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
async def _(bot: T_Bot, event: T_MessageEvent, matcher: Matcher):
    # 使用git pull更新

    ulang = get_user_lang(str(event.user.id if isinstance(event, satori.event.Event) else event.user_id))
    success, logs = update_liteyuki()
    reply = "Liteyuki updated!\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.btn_cmd(ulang.get("liteyuki.restart_now"), "reload-liteyuki")
    pip.main(["install", "-r", "requirements.txt"])
    reply += f"{ulang.get('liteyuki.update_restart', RESTART=btn_restart)}"
    # await md.send_md(reply, bot)
    img_bytes = await md_to_pic(reply)
    await UniMessage.send(UniMessage.image(raw=img_bytes))


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
    command=Alconna(
        "liteyuki-docs",
    ),
    aliases={"轻雪文档"},
).handle()
# Satori OK
async def _(matcher: Matcher):
    await matcher.finish("https://bot.liteyuki.icu/")


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
