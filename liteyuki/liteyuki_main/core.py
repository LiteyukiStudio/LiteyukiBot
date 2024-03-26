from nonebot import require
from nonebot.permission import SUPERUSER
from git import Repo

from liteyuki.utils.config import config
from liteyuki.utils.ly_typing import T_Bot, T_MessageEvent

from liteyuki.utils.language import get_user_lang
from liteyuki.utils.message import Markdown as md, send_markdown

from .reloader import Reloader

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna

cmd_liteyuki = on_alconna(
    Alconna(
        "liteyuki"
    ),
    permission=SUPERUSER
)

update_liteyuki = on_alconna(
    Alconna(
        ["update-liteyuki", "更新轻雪"]
    ),
    permission=SUPERUSER
)

reload_liteyuki = on_alconna(
    Alconna(
        ["reload-liteyuki", "restart-liteyuki", "重启轻雪"]
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
    logs = repo.index.diff()
    reply = "Liteyuki updated!\n"
    reply += f"```\n{logs}\n```\n"
    btn_restart = md.button(ulang.get("liteyuki.restart"), "restart-liteyuki")
    reply += f"{ulang.get('liteyuki.update_restart', RESTART=btn_restart)}"
    await send_markdown(reply, bot, event=event, at_sender=False)


@reload_liteyuki.handle()
async def _():
    await reload_liteyuki.send("Liteyuki reloading")
    Reloader.reload(3)
