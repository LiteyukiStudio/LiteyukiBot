"""LiteyukiBot v6-compatible session identity models.

The compatible field layout derives from nonebot-plugin-uninfo models.

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

from __future__ import annotations

from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, ConfigDict


class LegacySessionModel(BaseModel):
    """Represent the validated legacy session model contract."""
    model_config = ConfigDict(extra="ignore")


class SceneType(IntEnum):
    """Enumerate the supported scene type values."""
    PRIVATE = 0
    GROUP = 1
    GUILD = 2
    CHANNEL_TEXT = 3
    CHANNEL_CATEGORY = 4
    CHANNEL_VOICE = 5


class User(LegacySessionModel):
    """Represent the validated user contract."""
    id: str
    name: str | None = None
    nick: str | None = None
    avatar: str | None = None
    gender: str | None = None


class Scene(LegacySessionModel):
    """Represent the validated scene contract."""
    id: str
    type: SceneType
    name: str | None = None
    avatar: str | None = None
    parent: Scene | None = None


class Role(LegacySessionModel):
    """Represent the validated role contract."""
    id: str
    level: int | None = None
    name: str | None = None


class Member(LegacySessionModel):
    """Represent the validated member contract."""
    user: User
    nickname: str | None = None
    role: Role | None = None
    mute: bool | None = None
    joined_at: datetime | None = None


class Session(LegacySessionModel):
    """Represent the validated session contract."""
    self_id: str
    adapter: str
    scope: SceneType
    scene: Scene
    user: User
    member: Member | None = None
    operator: Member | None = None

    @property
    def session_id(self) -> str:
        """Return the session's session id.

        Returns:
            The `str` result produced by the operation.
        """
        if self.scope is SceneType.PRIVATE:
            target = self.user.id
        else:
            target = self.scene.id
        return f"{self.scope.value}:{target}"

    @property
    def target_id(self) -> str:
        """Return the session's target id.

        Returns:
            The `str` result produced by the operation.
        """
        if self.scope is SceneType.PRIVATE:
            return f"{self.scope.value}:{self.user.id}"
        return f"{self.scope.value}:{self.scene.id}:{self.user.id}"


__all__ = ["Member", "Role", "Scene", "SceneType", "Session", "User"]
