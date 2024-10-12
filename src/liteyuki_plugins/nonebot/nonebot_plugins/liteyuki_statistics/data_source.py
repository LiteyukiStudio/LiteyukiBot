import time
from typing import Any

from collections import Counter

from nonebot import Bot

from src.utils.message.html_tool import template2image
from .common import MessageEventModel, msg_db
from src.utils.base.language import Language
from src.utils.base.resource import get_path
from src.utils.message.string_tool import convert_seconds_to_time
from src.utils.external.logo import get_group_icon, get_user_icon


async def count_msg_by_bot_id(bot_id: str) -> int:
    condition = " AND bot_id = ?"
    condition_args = [bot_id]

    msg_rows = msg_db.where_all(
        MessageEventModel(),
        condition,
        *condition_args
    )

    return len(msg_rows)


async def get_stat_msg_image(
        duration: int,
        period: int,
        group_id: str = None,
        bot_id: str = None,
        user_id: str = None,
        ulang: Language = Language()
) -> bytes:
    """
    获取统计消息
    Args:
        user_id:
        ulang:
        bot_id:
        group_id:
        duration: 统计时间，单位秒
        period: 统计周期，单位秒

    Returns:
        tuple: [int,], [int,] 两个列表，分别为周期中心时间戳和消息数量
    """
    now = int(time.time())
    start_time = (now - duration)

    condition = "time > ?"
    condition_args = [start_time]

    if group_id:
        condition += " AND group_id = ?"
        condition_args.append(group_id)
    if bot_id:
        condition += " AND bot_id = ?"
        condition_args.append(bot_id)

    if user_id:
        condition += " AND user_id = ?"
        condition_args.append(user_id)

    msg_rows = msg_db.where_all(
        MessageEventModel(),
        condition,
        *condition_args
    )
    if not msg_rows:
        msg_rows = []
    timestamps = []
    msg_count = []
    msg_rows.sort(key=lambda x: x.time)

    start_time = max(msg_rows[0].time, start_time)

    for i in range(start_time, now, period):
        timestamps.append(i + period // 2)
        msg_count.append(0)

    for msg in msg_rows:
        period_start_time = start_time + (msg.time - start_time) // period * period
        period_center_time = period_start_time + period // 2
        index = timestamps.index(period_center_time)
        msg_count[index] += 1

    templates = {
            "data": [
                    {
                            "name"  : ulang.get("stat.message")
                                      + f"    Period {convert_seconds_to_time(period)}" + f"    Duration {convert_seconds_to_time(duration)}"
                                      + (f"    Group {group_id}" if group_id else "") + (f"    Bot {bot_id}" if bot_id else "") + (
                                              f"    User {user_id}" if user_id else ""),
                            "times" : timestamps,
                            "counts": msg_count
                    }
            ]
    }

    return await template2image(get_path("templates/stat_msg.html"), templates)


async def get_stat_rank_image(
        rank_type: str,
        limit: dict[str, Any],
        ulang: Language = Language(),
        bot: Bot = None,
) -> bytes:
    if rank_type == "user":
        condition = "user_id != ''"
        condition_args = []
    else:
        condition = "group_id != ''"
        condition_args = []

    for k, v in limit.items():
        match k:
            case "user_id":
                condition += " AND user_id = ?"
                condition_args.append(v)
            case "group_id":
                condition += " AND group_id = ?"
                condition_args.append(v)
            case "bot_id":
                condition += " AND bot_id = ?"
                condition_args.append(v)
            case "duration":
                condition += " AND time > ?"
                condition_args.append(v)

    msg_rows = msg_db.where_all(
        MessageEventModel(),
        condition,
        *condition_args
    )

    """
        {
            name: string,   # user name or group name
            count: int,     # message count
            icon: string    # icon url
        }
    """

    if rank_type == "user":
        ranking_counter = Counter([msg.user_id for msg in msg_rows])
    else:
        ranking_counter = Counter([msg.group_id for msg in msg_rows])
    sorted_data = sorted(ranking_counter.items(), key=lambda x: x[1], reverse=True)

    ranking: list[dict[str, Any]] = [
            {
                    "name" : _[0],
                    "count": _[1],
                    "icon" : await (get_group_icon(platform="qq", group_id=_[0]) if rank_type == "group" else get_user_icon(
                        platform="qq", user_id=_[0]
                    ))
            }
            for _ in sorted_data[0:min(len(sorted_data), limit["rank"])]
    ]

    templates = {
            "data":
                {
                        "name"   : ulang.get("stat.rank") + f"    Type {rank_type}" + f"    Limit {limit}",
                        "ranking": ranking
                }

    }

    return await template2image(get_path("templates/stat_rank.html"), templates, debug=True)
