import time
from typing import Any

from liteyuki.utils.message.html_tool import template2image
from .common import MessageEventModel, msg_db
from liteyuki.utils.base.language import Language
from liteyuki.utils.base.resource import get_path
from liteyuki.utils.message.npl import convert_seconds_to_time
from contextvars import ContextVar


async def count_msg_by_bot_id(bot_id: str) -> int:
    condition = " AND bot_id = ?"
    condition_args = [bot_id]

    msg_rows = msg_db.where_all(
        MessageEventModel(),
        condition,
        *condition_args
    )

    return len(msg_rows)


async def get_stat_msg_image(duration: int, period: int, group_id: str = None, bot_id: str = None, user_id: str = None,
                             ulang: Language = Language()) -> bytes:
    """
    获取统计消息
    Args:
        ctx:
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
                "name": ulang.get("stat.message")
                        + f"    Period {convert_seconds_to_time(period)}" + f"    Duration {convert_seconds_to_time(duration)}"
                        + (f"    Group {group_id}" if group_id else "") + (f"    Bot {bot_id}" if bot_id else ""),
                "times": timestamps,
                "counts": msg_count
            }
        ]
    }

    return await template2image(get_path("templates/stat_msg.html"), templates, debug=True)

    # if not timestamps or period_start_time != timestamps[-1]:
    #     timestamps.append(period_start_time)
    #     msg_count.append(1)
    # else:
    #     msg_count[-1] += 1
    #
