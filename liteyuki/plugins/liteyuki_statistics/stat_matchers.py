from nonebot import require
from liteyuki.internal.message.npl import convert_duration
from .stat_api import *

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import on_alconna, Alconna, Args, Subcommand, Arparma, Option

stat_msg = on_alconna(
    Alconna(
        "stat",
        Subcommand(
            "message",
            Args["duration", str, "1d"],  # 默认为1天
            Option(
                "-b|--bot",  # 生成图表
                Args["bot_id", str, ""],
                help_text="是否指定机器人",
            ),
            Option(
                "-g|--group",
                Args["group_id", str, ""],
                help_text="指定群组"
            ),
            Option(
                "-c|--chart",  # 生成图表
                help_text="是否生成图表",
            ),
            alias={"msg", "m"},
            help_text="查看统计次数内的消息"
        )
    )
)


@stat_msg.assign("message")
async def _(result: Arparma):
    args = result.subcommands.get("message").args
    options = result.subcommands.get("message").options
    duration = convert_duration(args.get("duration"), 86400)  # 秒数
    enable_chart = options.get("chart")

    if options.get("group"):
        group_id = options["group"].args.get("group_id")
    else:
        msg_rows = get_stat_msg_data(duration)
