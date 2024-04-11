import base64
import time
from typing import Any

import nonebot
import pip
from nonebot import Bot, get_driver, require
from nonebot.exception import MockApiException
from nonebot.internal.matcher import Matcher
from nonebot.permission import SUPERUSER

from liteyuki.utils.config import get_config, load_from_yaml
from liteyuki.utils.data_manager import StoredConfig, TempConfig, common_db
from liteyuki.utils.language import get_user_lang
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent
from liteyuki.utils.message import Markdown as md, broadcast_to_superusers
from liteyuki.utils.reloader import Reloader
from .api import update_liteyuki

require("nonebot_plugin_alconna"), require("nonebot_plugin_apscheduler")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma
from nonebot_plugin_apscheduler import scheduler

driver = get_driver()

markdown_image = common_db.first(StoredConfig(), default=StoredConfig()).config.get("markdown_image", False)


@on_alconna(
    command=Alconna(
        "liteecho",
    ),
    permission=SUPERUSER
).handle()
async def _(bot: T_Bot, matcher: Matcher):
    await matcher.finish(f"Hello, Liteyuki!\nBot {bot.self_id}")


@on_alconna(
    aliases={"更新轻雪"},
    command=Alconna(
        "update-liteyuki"
    ),
    permission=SUPERUSER
).handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    # 使用git pull更新
    ulang = get_user_lang(str(event.user_id))
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
async def _(matcher: Matcher, bot: T_Bot, event: T_MessageEvent):
    await matcher.send("Liteyuki reloading")
    temp_data = common_db.first(TempConfig(), default=TempConfig())
    temp_data.data["reload"] = True
    temp_data.data["reload_time"] = time.time()
    temp_data.data["reload_bot_id"] = bot.self_id
    temp_data.data["reload_session_type"] = event.message_type
    temp_data.data["reload_session_id"] = event.group_id if event.message_type == "group" else event.user_id
    temp_data.data["delta_time"] = 0
    common_db.upsert(temp_data)
    Reloader.reload(0)


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
            alias=["查询"]
        )
    ),
    permission=SUPERUSER
).handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot, matcher: Matcher):
    ulang = get_user_lang(str(event.user_id))
    stored_config: StoredConfig = common_db.first(StoredConfig(), default=StoredConfig())
    if result.subcommands.get("set"):
        key, value = result.subcommands.get("set").args.get("key"), result.subcommands.get("set").args.get("value")
        try:
            value = eval(value)
        except:
            pass
        stored_config.config[key] = value
        common_db.upsert(stored_config)
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
                    reply += f"\n{k}={v}"
                reply += "\n```"
        await md.send_md(reply, bot, event=event)


@on_alconna(
    aliases={"切换图片模式"},
    command=Alconna(
        "switch-image-mode"
    ),
    permission=SUPERUSER
).handle()
async def _(event: T_MessageEvent, matcher: Matcher):
    global markdown_image
    # 切换图片模式，False以图片形式发送，True以markdown形式发送
    ulang = get_user_lang(str(event.user_id))
    stored_config: StoredConfig = common_db.first(StoredConfig(), default=StoredConfig())
    stored_config.config["markdown_image"] = not stored_config.config.get("markdown_image", False)
    markdown_image = stored_config.config["markdown_image"]
    common_db.upsert(stored_config)
    await matcher.finish(ulang.get("liteyuki.image_mode_on" if stored_config.config["markdown_image"] else "liteyuki.image_mode_off"))


@on_alconna(
    command=Alconna(
        "liteyuki-docs",
    ),
    aliases={"轻雪文档"},
).handle()
async def _(matcher: Matcher):
    await matcher.finish("https://bot.liteyuki.icu/usage")


# system hook
@Bot.on_calling_api  # 图片模式检测
async def test_for_md_image(bot: T_Bot, api: str, data: dict):
    # 截获大图发送，转换为markdown发送
    if api in ["send_msg", "send_private_msg", "send_group_msg"] and markdown_image and data.get("user_id") != bot.self_id:
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
                result = await md.send_md(await md.image_async(file), bot, message_type=session_type, session_id=session_id)
            elif file.startswith("file"):
                file = file.replace("file://", "")
                result = await md.send_image(open(file, "rb").read(), bot, message_type=session_type, session_id=session_id)
            elif file.startswith("base64"):
                file_bytes = base64.b64decode(file.replace("base64://", ""))
                result = await md.send_image(file_bytes, bot, message_type=session_type, session_id=session_id)
            else:
                return
            raise MockApiException(result=result)


@driver.on_startup
async def on_startup():
    temp_data = common_db.first(TempConfig(), default=TempConfig())
    # 储存重启信息
    if temp_data.data.get("reload", False):
        delta_time = time.time() - temp_data.data.get("reload_time", 0)
        temp_data.data["delta_time"] = delta_time
        common_db.upsert(temp_data)  # 更新数据


@driver.on_shutdown
async def on_shutdown():
    pass


@driver.on_bot_connect
async def _(bot: T_Bot):
    temp_data = common_db.first(TempConfig(), default=TempConfig())
    # 用于重启计时
    if temp_data.data.get("reload", False):
        temp_data.data["reload"] = False
        reload_bot_id = temp_data.data.get("reload_bot_id", 0)
        if reload_bot_id != bot.self_id:
            return
        reload_session_type = temp_data.data.get("reload_session_type", "private")
        reload_session_id = temp_data.data.get("reload_session_id", 0)
        delta_time = temp_data.data.get("delta_time", 0)
        common_db.upsert(temp_data)  # 更新数据
        await bot.call_api(
            "send_msg",
            message_type=reload_session_type,
            user_id=reload_session_id,
            group_id=reload_session_id,
            message="Liteyuki reloaded in %.2f s" % delta_time
        )


# 每天4点更新
@scheduler.scheduled_job("cron", hour=4)
async def every_day_update():
    if get_config("auto_update"):
        result, logs = update_liteyuki()
        if result:
            await broadcast_to_superusers(f"Liteyuki updated: ```\n{logs}\n```")
            nonebot.logger.info(f"Liteyuki updated: {logs}")
            Reloader.reload(1)
        else:
            nonebot.logger.info(logs)
