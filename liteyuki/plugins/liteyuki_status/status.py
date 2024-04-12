from nonebot import require

require("nonebot_plugin_alconna")
from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma

status_alc = on_alconna(
    aliases={"status"},
    command=Alconna(
        "status",
        Subcommand(
            "memory",
            alias={"mem", "m", "内存"},
        ),
        Subcommand(
            "process",
            alias={"proc", "p", "进程"},
        )
    ),
)


@status_alc.assign("memory")
async def _():
    print("memory")


@status_alc.assign("process")
async def _():
    print("process")
