from typing import Any

import nonebot
import pip
from git import Repo
from nonebot import require, get_driver
from nonebot.permission import SUPERUSER

from liteyuki.utils.config import config, load_from_yaml
from liteyuki.utils.data_manager import StoredConfig, common_db
from liteyuki.utils.language import get_user_lang
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent
from liteyuki.utils.message import Markdown as md
from .reloader import Reloader
from liteyuki.utils import htmlrender

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma

driver = get_driver()

cmd_liteyuki = on_alconna(
    Alconna(
        "liteyuki"
    ),
    permission=SUPERUSER
)

update_liteyuki = on_alconna(
    aliases={"更新轻雪"},
    command=Alconna(
        "update-liteyuki"
    ),
    permission=SUPERUSER
)

reload_liteyuki = on_alconna(
    aliases={"重启轻雪"},
    command=Alconna(
        "reload-liteyuki"
    ),
    permission=SUPERUSER
)

cmd_config = on_alconna(
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
)

switch_image_mode = on_alconna(
    aliases={"切换图片模式"},
    command=Alconna(
        "switch-image-mode"
    ),
    permission=SUPERUSER
)


@cmd_liteyuki.handle()
async def _(bot: T_Bot):
    await cmd_liteyuki.finish(f"Hello, Liteyuki!\nBot {bot.self_id}\nLiteyukiID {config.get('liteyuki_id', 'No')}")


@update_liteyuki.handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    # 使用git pull更新
    ulang = get_user_lang(str(event.user_id))
    origins = ["origin", "origin2"]
    repo = Repo(".")
    for origin in origins:
        try:
            repo.remotes[origin].pull()
            break
        except Exception as e:
            print(f"Pull from {origin} failed: {e}")
    logs = repo.index
    reply = "Liteyuki updated!\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.button(ulang.get("liteyuki.restart_now"), "restart-liteyuki")
    pip.main(["install", "-r", "requirements.txt"])
    reply += f"{ulang.get('liteyuki.update_restart', RESTART=btn_restart)}"
    await md.send_md(reply, bot, event=event, at_sender=False)


@reload_liteyuki.handle()
async def _():
    await reload_liteyuki.send("Liteyuki reloading")
    Reloader.reload(3)


@cmd_config.handle()
async def _(result: Arparma, event: T_MessageEvent, bot: T_Bot):
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
        await cmd_config.finish(f"{ulang.get('liteyuki.config_set_success', KEY=key, VAL=value)}")
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


@switch_image_mode.handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    ulang = get_user_lang(str(event.user_id))
    stored_config: StoredConfig = common_db.first(StoredConfig(), default=StoredConfig())
    stored_config.config["markdown_image"] = not stored_config.config.get("markdownimage", False)
    common_db.upsert(stored_config)
    await switch_image_mode.finish(f"{ulang.get('liteyuki.image_mode_switched', MODE=ulang.get('liteyuki.image_mode_on') if stored_config.config.get('image_mode') else ulang.get('liteyuki.image_mode_off'))}")

@driver.on_startup
async def on_startup():
    htmlrender.browser = await htmlrender.get_browser()
    nonebot.logger.info("Browser Started.")


@driver.on_shutdown
async def on_shutdown():
    await htmlrender.shutdown_browser()
    nonebot.logger.info("Browser Stopped.")
