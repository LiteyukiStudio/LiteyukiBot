# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:47
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : event.py
@Software: PyCharm
"""
from typing import Any

from liteyuki.comm.storage import shared_memory


class Event:
    def __init__(self, type: str, data: dict[str, Any], bot_id: str, session_id: str, session_type: str, receive_channel: str = "event_to_nonebot"):
        """
        事件
        Args:
            type: 类型
            data: 数据
            bot_id: 机器人ID
            session_id: 会话ID
            session_type: 会话类型
            receive_channel: 接收频道
        """
        self.type = type
        self.data = data
        self.bot_id = bot_id
        self.session_id = session_id
        self.session_type = session_type
        self.receive_channel = receive_channel

    def __str__(self):
        return f"Event(type={self.type}, data={self.data}, bot_id={self.bot_id}, session_id={self.session_id}, session_type={self.session_type})"

    def reply(self, message: str | dict[str, Any]):
        """
        回复消息
        Args:
            message:
        Returns:
        """
        to_nonebot_event = Event(
            type=self.session_type,
            data={
                    "message": message
            },
            bot_id=self.bot_id,
            session_id=self.session_id,
            session_type=self.session_type,
            receive_channel="_"
        )
        print(to_nonebot_event)
        shared_memory.publish(self.receive_channel, to_nonebot_event)
