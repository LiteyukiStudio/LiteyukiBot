import time
from typing import Any
from .common import MessageEventModel, msg_db


def get_stat_msg_data(duration, period) -> tuple[list[int,], list[int,]]:
    """
    获取统计消息
    Args:
        duration: 统计时间，单位秒
        period: 统计周期，单位秒

    Returns:
        tuple: [int,], [int,] 两个列表，分别为周期中心时间戳和消息数量
    """
    now = int(time.time())
    msg_rows = msg_db.where_all(
        MessageEventModel(),
        "time > ?",
        now - duration
    )
    timestamps = []
    msg_count = []
    msg_rows.sort(key=lambda x: x.time)
    for msg_row in msg_rows:
        period_center_time = msg_row.time - msg_row.time % period + period // 2

        # if not timestamps or period_start_time != timestamps[-1]:
        #     timestamps.append(period_start_time)
        #     msg_count.append(1)
        # else:
        #     msg_count[-1] += 1
        #
