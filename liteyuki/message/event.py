# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/8/19 下午10:47
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : event.py
@Software: PyCharm
"""
from typing import Any, Optional

from liteyuki import Channel
from liteyuki.comm.storage import shared_memory


class MessageEvent:
    def __init__(
            self,

            bot_id: str,
            message: list[dict[str, Any]] | str,
            message_type: str,
            raw_message: str,
            session_id: str,
            user_id: str,
            session_type: str,
            receive_channel: Optional[Channel["MessageEvent"]] = None,
            data: Optional[dict[str, Any]] = None,
    ):
        """
        轻雪抽象消息事件
        Args:

            bot_id: 机器人ID
            message: 消息，消息段数组[{type: str, data: dict[str, Any]}]
            raw_message: 原始消息(通常为纯文本的格式)
            message_type: 消息类型(private, group, other)

            session_id: 会话ID(私聊通常为用户ID，群聊通常为群ID)
            session_type: 会话类型(private, group)
            receive_channel: 接收频道(用于回复消息)

            data: 附加数据
        """

        if data is None:
            data = {}
        self.message_type = message_type
        self.data = data
        self.bot_id = bot_id

        self.message = message
        self.raw_message = raw_message

        self.session_id = session_id
        self.session_type = session_type
        self.user_id = user_id

        self.receive_channel = receive_channel

    def __str__(self):
        return (f"Event(message_type={self.message_type}, data={self.data}, bot_id={self.bot_id}, "
                f"session_id={self.session_id}, session_type={self.session_type})")

    def reply(self, message: str | dict[str, Any]):
        """
        回复消息
        Args:
            message:
        Returns:
        """
        reply_event = MessageEvent(
            message_type=self.session_type,
            message=message,
            raw_message="",
            data={
                    "message": message
            },
            bot_id=self.bot_id,
            session_id=self.session_id,
            user_id=self.user_id,
            session_type=self.session_type,
            receive_channel=None
        )
        # shared_memory.publish(self.receive_channel, reply_event)
        if self.receive_channel:
            self.receive_channel.send(reply_event)
