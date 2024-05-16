from nonebot import Bot, require
from liteyuki.utils.message.npl import convert_duration, convert_time_to_seconds
from .stat_api import *
from ...utils import satori_utils
from ...utils.base.language import Language
from ...utils.base.ly_typing import T_MessageEvent

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import UniMessage, on_alconna, Alconna, Args, Subcommand, Arparma, Option

stat_msg = on_alconna(
    Alconna(
        "statistic",
        Subcommand(
            "message",
            # Args["duration", str, "2d"]["period", str, "60s"],  # 默认为1天
            Option(
                "-d|--duration",
                Args["duration", str, "2d"],
                help_text="统计时间",
            ),
            Option(
                "-p|--period",
                Args["period", str, "60s"],
                help_text="统计周期",
            ),
            Option(
                "-b|--bot",  # 生成图表
                Args["bot_id", str, "current"],
                help_text="是否指定机器人",
            ),
            Option(
                "-g|--group",
                Args["group_id", str, "current"],
                help_text="指定群组"
            ),
            alias={"msg", "m"},
            help_text="查看统计次数内的消息"
        )
    ),
    aliases={"stat"}
)


@stat_msg.assign("message")
async def _(result: Arparma, event: T_MessageEvent, bot: Bot):
    ulang = Language(satori_utils.get_user_id(event))

    try:
        duration = convert_time_to_seconds(result.other_args.get("duration", "2d"))  # 秒数
        period = convert_time_to_seconds(result.other_args.get("period", "1m"))
    except BaseException as e:
        await stat_msg.send(ulang.get("liteyuki.invalid_command", TEXT=str(e.__str__())))
        return

    group_id = result.other_args.get("group_id")
    bot_id = result.other_args.get("bot_id")

    if group_id in ["current", "c"]:
        group_id = str(satori_utils.get_group_id(event))

    if group_id in ["all", "a"]:
        group_id = "all"

    if bot_id in ["current", "c"]:
        bot_id = str(bot.self_id)

    img = await get_stat_msg_image(duration, period, group_id, bot_id, ulang)
    await stat_msg.send(UniMessage.image(raw=img))
