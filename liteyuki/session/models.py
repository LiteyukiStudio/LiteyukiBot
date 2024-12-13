"""
本模块使用了[nonebot-plugin-uninfo](https://github.com/RF-Tar-Railt/nonebot-plugin-uninfo)的部分模型定义
MIT License

Copyright (c) 2024 RF-Tar-Railt

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel


class SceneType(int, Enum):
    PRIVATE = 0
    """私聊场景"""
    GROUP = 1
    """群聊场景"""
    GUILD = 2
    """频道场景"""
    CHANNEL_TEXT = 3
    """子频道文本场景"""
    CHANNEL_CATEGORY = 4
    """频道分类场景"""
    CHANNEL_VOICE = 5
    """子频道语音场景"""


class User(BaseModel):
    """
    用户信息
    Attributes:
        id: 用户ID
        name: 用户名
        nick: 用户昵称
        avatar: 用户头像图链接
    """

    id: str
    name: str | None = None
    nick: str | None = None
    avatar: str | None = None
    gender: str | None = None


class Scene(BaseModel):
    """
    场景信息
    Attributes:
        id: 场景ID
        type: 场景类型
        name: 场景名
        avatar: 场景头像图链接
        parent: 父场景
    """

    id: str
    type: SceneType
    name: str | None = None
    avatar: str | None = None
    parent: "Scene | None" = None


class Role(BaseModel):
    id: str
    level: int | None = None
    name: str | None = None


class Member(BaseModel):
    user: User
    nickname: str | None = None
    role: Role | None = None

    mute: bool | None = None
    joined_at: datetime | None = None


class Session(BaseModel):
    """
    会话信息
    Attributes:
        self_id: 机器人ID
        adapter: 适配器ID
        scope: 会话范围
        scene: 场景信息
        user: 用户信息
        member: 成员信息，仅频道及群聊有效
        operator: 操作者信息，仅频道及群聊有效

        session_id: 会话ID，精确到会话，用于快速标识会话，通常为{适配器范围}:{群聊ID(公共)/用户ID(群聊)}
        target_id: 目标ID，精确到用户，用于快速标识会话，通常为{适配器范围}:{群聊ID}:{用户ID}(仅公共) 或 {适配器范围}:{用户ID}(仅私聊)
    """

    self_id: str
    adapter: str
    scope: str
    scene: Scene
    user: User
    member: "Member | None" = None
    operator: "Member | None" = None

    @property
    def session_id(self):
        if self.scope == SceneType.PRIVATE:
            return f"{self.scope}:{self.user.id}"
        elif self.scope in (
            SceneType.GROUP,
            SceneType.GUILD,
            SceneType.CHANNEL_TEXT,
            SceneType.CHANNEL_VOICE,
            SceneType.CHANNEL_CATEGORY,
        ):
            return f"{self.scope}:{self.scene.id}"
        else:
            raise ValueError("Invalid SceneType")

    @property
    def target_id(self):
        if self.scope == SceneType.PRIVATE:
            return f"{self.scope}:{self.user.id}"
        elif self.scope in (
            SceneType.GROUP,
            SceneType.GUILD,
            SceneType.CHANNEL_TEXT,
            SceneType.CHANNEL_VOICE,
            SceneType.CHANNEL_CATEGORY,
        ):
            return f"{self.scope}:{self.scene.id}:{self.user.id}"
