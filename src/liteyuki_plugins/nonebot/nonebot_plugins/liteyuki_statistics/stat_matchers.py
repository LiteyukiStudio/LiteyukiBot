from nonebot import Bot, require
from src.utils.message.string_tool import convert_duration, convert_time_to_seconds
from .data_source import *
from src.utils import event as event_utils
from src.utils.base.language import Language
from src.utils.base.ly_typing import T_MessageEvent

require("nonebot_plugin_alconna")

from nonebot_plugin_alconna import (
    UniMessage,
    on_alconna,
    Alconna,
    Args,
    Subcommand,
    Arparma,
    Option,
    MultiVar
)

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
            Option(
                "-u|--user",
                Args["user_id", str, "current"],
                help_text="指定用户"
            ),
            alias={"msg", "m"},
            help_text="查看统计次数内的消息"
        ),
        Subcommand(
            "rank",
            Option(
                "-u|--user",
                help_text="以用户为指标",
            ),
            Option(
                "-g|--group",
                help_text="以群组为指标",
            ),
            Option(
                "-l|--limit",
                Args["limit", MultiVar(str)],
                help_text="限制参数，使用key=val格式",
            ),
            Option(
                "-d|--duration",
                Args["duration", str, "1d"],
                help_text="统计时间",
            ),
            Option(
                "-r|--rank",
                Args["rank", int, 20],
                help_text="指定排名",
            ),
            alias={"r"},
        )
    ),
    aliases={"stat"}
)


@stat_msg.assign("message")
async def _(result: Arparma, event: T_MessageEvent, bot: Bot):
    ulang = Language(event_utils.get_user_id(event))
    try:
        duration = convert_time_to_seconds(result.other_args.get("duration", "2d"))  # 秒数
        period = convert_time_to_seconds(result.other_args.get("period", "1m"))
    except BaseException as e:
        await stat_msg.send(ulang.get("liteyuki.invalid_command", TEXT=str(e.__str__())))
        return

    group_id = result.other_args.get("group_id")
    bot_id = result.other_args.get("bot_id")
    user_id = result.other_args.get("user_id")

    if group_id in ["current", "c"] and hasattr(event, "group_id"):
        group_id = str(event_utils.get_group_id(event))
    else:
        group_id = "all"

    if group_id in ["all", "a"]:
        group_id = "all"

    if bot_id in ["current", "c"]:
        bot_id = str(bot.self_id)

    if user_id in ["current", "c"]:
        user_id = str(event_utils.get_user_id(event))

    img = await get_stat_msg_image(duration=duration, period=period, group_id=group_id, bot_id=bot_id, user_id=user_id, ulang=ulang)
    await stat_msg.send(UniMessage.image(raw=img))


@stat_msg.assign("rank")
async def _(result: Arparma, event: T_MessageEvent, bot: Bot):
    ulang = Language(event_utils.get_user_id(event))
    rank_type = "user"
    duration = convert_time_to_seconds(result.other_args.get("duration", "1d"))
    if result.subcommands.get("rank").options.get("user"):
        rank_type = "user"
    elif result.subcommands.get("rank").options.get("group"):
        rank_type = "group"

    limit = result.other_args.get("limit", {})
    if limit:
        limit = dict([i.split("=") for i in limit])
    limit["duration"] = time.time() - duration  # 起始时间戳
    limit["rank"] = result.other_args.get("rank", 20)

    img = await get_stat_rank_image(rank_type=rank_type, limit=limit, ulang=ulang)
    await stat_msg.send(UniMessage.image(raw=img))
