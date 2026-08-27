"""Validated settings for one SnowLuma OneBot v11 endpoint."""

from __future__ import annotations

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class SnowLumaAccountSettings:
    implementation: Literal["snowluma"]
    self_id: str
    ws_url: str
    access_token: str | None = None

    def __post_init__(self) -> None:
        if self.implementation != "snowluma":
            raise ValueError("implementation must be the literal 'snowluma'")
        if isinstance(self.self_id, bool) or not isinstance(self.self_id, (str, int)):
            raise ValueError("self_id must be a non-empty string or integer")
        self_id = str(self.self_id)
        if not self_id or self_id != self_id.strip():
            raise ValueError("self_id must be a non-empty trimmed identifier")
        object.__setattr__(self, "self_id", self_id)
        _validate_ws_url(self.ws_url)
        if self.access_token is not None:
            token = self.access_token
            if (
                not token
                or token != token.strip()
                or any(ord(character) < 33 or ord(character) > 126 for character in token)
            ):
                raise ValueError("access_token must be a non-empty printable token when set")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> SnowLumaAccountSettings:
        unknown = set(value) - {"implementation", "self_id", "ws_url", "access_token"}
        if unknown:
            raise ValueError(f"unknown SnowLuma account settings: {', '.join(sorted(unknown))}")
        missing = {"implementation", "self_id", "ws_url"} - value.keys()
        if missing:
            raise ValueError(f"missing SnowLuma account settings: {', '.join(sorted(missing))}")
        return cls(
            implementation=cast(Literal["snowluma"], value["implementation"]),
            self_id=cast(str, value["self_id"]),
            ws_url=cast(str, value["ws_url"]),
            access_token=cast(str | None, value.get("access_token")),
        )


def _validate_ws_url(value: str) -> None:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        raise ValueError("ws_url must be a non-empty WebSocket URL without whitespace")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as error:
        raise ValueError("ws_url must be a valid WebSocket URL") from error
    if parsed.scheme not in {"ws", "wss"} or not hostname or parsed.username or parsed.password:
        raise ValueError("ws_url must be an absolute ws:// or wss:// URL without credentials")
    if parsed.scheme == "ws" and not _is_loopback(hostname):
        raise ValueError("ws:// is allowed only for loopback endpoints; use wss:// for remote hosts")


def _is_loopback(hostname: str) -> bool:
    if hostname.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname.split("%", 1)[0]).is_loopback
    except ValueError:
        return False


__all__ = ["SnowLumaAccountSettings"]
