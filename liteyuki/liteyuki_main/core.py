import base64
from typing import Any

import nonebot
import pip
from git import Repo
from nonebot import Bot, require, get_driver
from nonebot.exception import MockApiException
from nonebot.permission import SUPERUSER

from liteyuki.utils.config import config, load_from_yaml
from liteyuki.utils.data_manager import StoredConfig, common_db
from liteyuki.utils.language import get_user_lang
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent
from liteyuki.utils.message import Markdown as md
from liteyuki.utils.reloader import Reloader
from liteyuki.utils.resource import get_loaded_resource_packs, load_resources

require("nonebot_plugin_alconna"), require("nonebot_plugin_htmlrender")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma

driver = get_driver()

markdown_image = common_db.first(StoredConfig(), default=StoredConfig()).config.get("markdown_image", False)

liteyuki = on_alconna(
    command=Alconna(
        "liteecho",
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

reload_resources = on_alconna(
    aliases={"重载资源"},
    command=Alconna(
        "reload-resources"
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


@liteyuki.handle()
async def _(bot: T_Bot):
    await liteyuki.finish(f"Hello, Liteyuki!\nBot {bot.self_id}")


@update_liteyuki.handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    # 使用git pull更新
    ulang = get_user_lang(str(event.user_id))
    origins = ["origin", "origin2"]
    repo = Repo(".")

    # Get the current HEAD commit
    current_head_commit = repo.head.commit

    # Fetch the latest information from the cloud
    repo.remotes.origin.fetch()

    # Get the latest HEAD commit
    new_head_commit = repo.commit('origin/main')

    # If the new HEAD commit is different from the current HEAD commit, there is a new commit
    diffs = current_head_commit.diff(new_head_commit)
    logs = ""
    for diff in diffs.iter_change_type('M'):
        logs += f"\n{diff.a_path}"

    for origin in origins:
        try:
            repo.remotes[origin].pull()
            break
        except Exception as e:
            nonebot.logger.error(f"Pull from {origin} failed: {e}")
    reply = "Liteyuki updated!\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.cmd(ulang.get("liteyuki.restart_now"), "reload-liteyuki")
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


@reload_resources.handle()
async def _(event: T_MessageEvent):
    ulang = get_user_lang(str(event.user_id))
    load_resources()
    await reload_resources.finish(
        ulang.get("liteyuki.reload_resources_success",
                  NUM=len(get_loaded_resource_packs())
                  )
    )


@switch_image_mode.handle()
async def _(bot: T_Bot, event: T_MessageEvent):
    global markdown_image
    # 切换图片模式，False以图片形式发送，True以markdown形式发送
    ulang = get_user_lang(str(event.user_id))
    stored_config: StoredConfig = common_db.first(StoredConfig(), default=StoredConfig())
    stored_config.config["markdown_image"] = not stored_config.config.get("markdown_image", False)
    markdown_image = stored_config.config["markdown_image"]
    common_db.upsert(stored_config)
    await switch_image_mode.finish(ulang.get("liteyuki.image_mode_on" if stored_config.config["markdown_image"] else "liteyuki.image_mode_off"))


# system hook

@Bot.on_calling_api
async def test_for_md_image(bot: T_Bot, api: str, data: dict):
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
    pass


@driver.on_shutdown
async def on_shutdown():
    pass
