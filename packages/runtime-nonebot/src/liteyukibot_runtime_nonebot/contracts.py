"""Protocol-neutral contracts for NoneBot adapter events and actions."""

from __future__ import annotations

import importlib
import json
import math
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel

from liteyukibot.events import (
    ActorRef,
    ConversationRef,
    EventEnvelope,
    Message,
    Segment,
    SendMessage,
    canonical_source_event_id,
)

_MESSAGE_MODULES = {
    "onebot-v11": "nonebot.adapters.onebot.v11",
    "onebot-v12": "nonebot.adapters.onebot.v12",
    "satori": "nonebot.adapters.satori",
}
_MEDIA_TYPES = frozenset({"image", "audio", "voice", "video", "file"})


class AdapterContractError(ValueError):
    """An Action cannot be represented by the selected adapter contract."""


def adapter_id(display_name: str) -> str:
    """Implement the adapter id operation for the component.

    Args:
        display_name: The display name value used by the operation.

    Returns:
        The `str` result produced by the operation.
    """
    normalized = "-".join(display_name.strip().lower().replace("_", "-").split())
    aliases = {
        "onebot-v11": "onebot-v11",
        "onebot-v12": "onebot-v12",
        "satori": "satori",
    }
    return aliases.get(normalized, normalized)


def normalize_event(bot: Any, event: Any, *, runtime_id: str | None = None) -> EventEnvelope:
    """Normalize event.

    Args:
        bot: The bot value used by the operation.
        event: Event associated with the operation.
        runtime_id: Stable runtime identifier.

    Returns:
        The `EventEnvelope` result produced by the operation.
    """
    adapter = adapter_id(str(bot.adapter.get_name()))
    bot_id = str(bot.self_id)
    native_message = _original_message(event)
    timestamp = _event_timestamp(event)
    raw = _event_raw(event)
    runtime_name = runtime_id if runtime_id is not None else os.environ.get("LITEYUKI_RUNTIME_ID", "nonebot")
    upstream_id = _upstream_event_id(raw)
    values: dict[str, Any] = {
        "id": canonical_source_event_id(runtime_name, f"{adapter}:{bot_id}", upstream_id),
        "runtime_id": runtime_name,
        "adapter": adapter,
        "bot_id": bot_id,
        "type": _event_name(event),
        "conversation": _conversation(adapter, bot_id, event),
        "actor": _actor(adapter, bot_id, event),
        "message": _to_portable_message(adapter, native_message) if native_message is not None else None,
        "reply_token": str(uuid4()) if native_message is not None else None,
        "raw": raw,
    }
    if timestamp is not None:
        values["timestamp"] = timestamp
    return EventEnvelope.model_validate(values)


def to_native_message(adapter: str, message: Message) -> Any:
    """Convert the value to native message.

    Args:
        adapter: The adapter value used by the operation.
        message: Message content associated with the operation.

    Returns:
        The `Any` result produced by the operation.
    """
    module_name = _MESSAGE_MODULES.get(adapter)
    if module_name is None:
        raise AdapterContractError(f"structured messages are unsupported for adapter {adapter!r}")
    module = importlib.import_module(module_name)
    message_class = module.Message
    segment_class = module.MessageSegment
    segments = [_to_native_segment(adapter, segment_class, segment) for segment in message.segments]
    return message_class(segments)


async def send_proactive(bot: Any, adapter: str, action: SendMessage, message: Any) -> Any:
    """Send proactive.

    Args:
        bot: The bot value used by the operation.
        adapter: The adapter value used by the operation.
        action: Action request being processed.
        message: Message content associated with the operation.

    Returns:
        The `Any` result produced by the operation.
    """
    conversation = action.conversation
    if conversation is None:
        raise AdapterContractError("proactive sends require a conversation")

    if adapter == "onebot-v11":
        target_id = _positive_integer_id(conversation.id)
        if conversation.type == "private":
            return await bot.call_api("send_private_msg", user_id=target_id, message=message)
        if conversation.type == "group":
            return await bot.call_api("send_group_msg", group_id=target_id, message=message)
        raise AdapterContractError(f"OneBot v11 proactive sends do not support {conversation.type!r} conversations")

    if adapter == "onebot-v12":
        params: dict[str, Any] = {"detail_type": conversation.type, "message": message}
        if conversation.type == "private":
            params["user_id"] = conversation.id
        elif conversation.type == "group":
            params["group_id"] = conversation.id
        elif conversation.type == "channel":
            if not conversation.parent_id:
                raise AdapterContractError("OneBot v12 channel sends require conversation.parent_id")
            params["guild_id"] = conversation.parent_id
            params["channel_id"] = conversation.id
        else:
            raise AdapterContractError(f"OneBot v12 proactive sends do not support {conversation.type!r} conversations")
        return await bot.call_api("send_message", **params)

    if adapter == "satori":
        if conversation.type not in {"private", "channel"}:
            raise AdapterContractError(
                f"Satori proactive sends require a private or channel conversation, got {conversation.type!r}"
            )
        return await bot.send_message(conversation.id, message)

    raise AdapterContractError(f"proactive sends are unsupported for adapter {adapter!r}")


def json_value(value: Any) -> Any:
    """Implement the json value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.
    """
    normalized = _normalize_json(value)
    encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
    return json.loads(encoded)


def _normalize_json(value: Any) -> Any:
    """Normalize json.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_normalize_json`. It delegates to `_normalize_json`,
        `model_dump`, `isoformat`, `_aware_utc` while keeping intermediate state local to the owning
        operation.
    """
    if isinstance(value, BaseModel):
        return _normalize_json(value.model_dump(mode="python"))
    if isinstance(value, datetime):
        return _aware_utc(value).isoformat()
    if isinstance(value, Enum):
        return _normalize_json(value.value)
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("JSON results must not contain NaN or infinity")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON results must use string object keys")
        return {key: _normalize_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json(item) for item in value]
    raise TypeError(f"Action result contains non-JSON value {type(value).__name__}")


def _event_timestamp(event: Any) -> datetime | None:
    """Implement the event timestamp operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `datetime | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_event_timestamp`. It delegates to `getattr`, `_aware_utc`,
        `fromtimestamp` while keeping intermediate state local to the owning operation.
    """
    value = getattr(event, "time", None)
    if value is None:
        value = getattr(event, "timestamp", None)
    if isinstance(value, datetime):
        return _aware_utc(value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, UTC)
    return None


def _aware_utc(value: datetime) -> datetime:
    """Implement the aware utc operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `datetime` result produced by the operation.

    Notes:
        Internal implementation detail for `_aware_utc`. It delegates to `utcoffset`, `astimezone`,
        `fromtimestamp`, `timestamp` while keeping intermediate state local to the owning operation.
    """
    if value.tzinfo is not None and value.utcoffset() is not None:
        return value.astimezone(UTC)
    return datetime.fromtimestamp(value.timestamp(), UTC)


def _event_name(event: Any) -> str:
    """Implement the event name operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_event_name`. It delegates to `get_event_name` while keeping
        intermediate state local to the owning operation.
    """
    try:
        return str(event.get_event_name())
    except AttributeError, NotImplementedError, TypeError, ValueError:
        return type(event).__name__


def _conversation(adapter: str, bot_id: str, event: Any) -> ConversationRef:
    """Implement the conversation operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        bot_id: Stable identifier for the bot.
        event: Event associated with the operation.

    Returns:
        The `ConversationRef` result produced by the operation.

    Notes:
        Internal implementation detail for `_conversation`. It delegates to `_string_attribute`,
        `getattr`, `_integer_value`, `_context_actor_id` while keeping intermediate state local to the
        owning operation.
    """
    if adapter in {"onebot-v11", "onebot-v12"}:
        channel_id = _string_attribute(event, "channel_id")
        if channel_id:
            return ConversationRef(
                id=channel_id,
                type="channel",
                parent_id=_string_attribute(event, "guild_id"),
            )
        group_id = _string_attribute(event, "group_id")
        if group_id:
            return ConversationRef(id=group_id, type="group")
        user_id = _string_attribute(event, "user_id")
        if user_id:
            return ConversationRef(id=user_id, type="private")

    if adapter == "satori":
        channel = getattr(event, "channel", None)
        channel_id = _string_attribute(channel, "id")
        if channel_id:
            channel_type = getattr(channel, "type", None)
            kind: Literal["private", "channel"] = "private" if _integer_value(channel_type) == 1 else "channel"
            guild = getattr(event, "guild", None)
            parent_id = _string_attribute(channel, "parent_id") or _string_attribute(guild, "id")
            return ConversationRef(id=channel_id, type=kind, parent_id=parent_id)
        guild_id = _string_attribute(getattr(event, "guild", None), "id")
        if guild_id:
            return ConversationRef(id=guild_id, type="group")
        actor_id = _context_actor_id(event)
        if actor_id:
            return ConversationRef(id=actor_id, type="private")

    try:
        session_id = str(event.get_session_id())
    except AttributeError, NotImplementedError, TypeError, ValueError:
        session_id = ""
    return ConversationRef(id=session_id or f"bot:{bot_id}")


def _actor(adapter: str, bot_id: str, event: Any) -> ActorRef | None:
    """Implement the actor operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        bot_id: Stable identifier for the bot.
        event: Event associated with the operation.

    Returns:
        The `ActorRef | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_actor`. It delegates to `_context_actor_id`, `getattr`,
        `_string_attribute`, `bool` while keeping intermediate state local to the owning operation.
    """
    actor_id = _context_actor_id(event)
    if not actor_id:
        return None

    display_name: str | None = None
    is_bot = actor_id == bot_id
    if adapter == "onebot-v11":
        sender = getattr(event, "sender", None)
        display_name = _string_attribute(sender, "card") or _string_attribute(sender, "nickname")
    elif adapter == "satori":
        member = getattr(event, "member", None)
        user = getattr(event, "user", None) or getattr(event, "operator", None)
        display_name = (
            _string_attribute(member, "nick") or _string_attribute(user, "nick") or _string_attribute(user, "name")
        )
        explicit_is_bot = getattr(user, "is_bot", None)
        if explicit_is_bot is not None:
            is_bot = bool(explicit_is_bot)
        else:
            login_user = getattr(getattr(event, "login", None), "user", None)
            is_bot = actor_id == _string_attribute(login_user, "id")
    return ActorRef(id=actor_id, display_name=display_name, is_bot=is_bot)


def _context_actor_id(event: Any) -> str | None:
    """Implement the context actor id operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `str | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_context_actor_id`. It delegates to `_string_attribute`,
        `getattr`, `get_user_id` while keeping intermediate state local to the owning operation.
    """
    actor_id = _string_attribute(event, "user_id")
    if actor_id:
        return actor_id
    user = getattr(event, "user", None) or getattr(event, "operator", None)
    actor_id = _string_attribute(user, "id")
    if actor_id:
        return actor_id
    try:
        return str(event.get_user_id()) or None
    except AttributeError, NotImplementedError, TypeError, ValueError:
        return None


def _original_message(event: Any) -> Any | None:
    """Implement the original message operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `Any | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_original_message`. It delegates to `getattr`, `get_message`
        while keeping intermediate state local to the owning operation.
    """
    original = getattr(event, "original_message", None)
    if original is not None:
        return original
    try:
        return event.get_message()
    except AttributeError, NotImplementedError, TypeError, ValueError:
        return None


def _to_portable_message(adapter: str, native_message: Any) -> Message:
    """Implement the to portable message operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        native_message: The native message value used by the operation.

    Returns:
        The `Message` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_portable_message`. It delegates to
        `_to_portable_segment` while keeping intermediate state local to the owning operation.
    """
    return Message(segments=tuple(_to_portable_segment(adapter, segment) for segment in native_message))


def _to_portable_segment(adapter: str, native_segment: Any) -> Segment:
    """Implement the to portable segment operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        native_segment: The native segment value used by the operation.

    Returns:
        The `Segment` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_portable_segment`. It delegates to `_native_data`,
        `getattr`, `model_dump`, `_to_portable_message` while keeping intermediate state local to the
        owning operation.
    """
    native_type = str(native_segment.type)
    data = _native_data(adapter, native_type, getattr(native_segment, "data", {}))
    children = getattr(native_segment, "children", None)
    portable_children = (
        [segment.model_dump(mode="json") for segment in _to_portable_message(adapter, children).segments]
        if children
        else []
    )

    if native_type == "text":
        return Segment(type="text", data=data)

    if (
        (adapter == "onebot-v11" and native_type == "at")
        or (adapter == "onebot-v12" and native_type in {"mention", "mention_all"})
        or (adapter == "satori" and native_type == "at")
    ):
        return Segment(type="mention", data=_portable_mention(adapter, native_type, data))

    if (adapter in {"onebot-v11", "onebot-v12"} and native_type == "reply") or (
        adapter == "satori" and native_type == "quote"
    ):
        reply = _portable_reply(adapter, data)
        if portable_children:
            reply["children"] = portable_children
        return Segment(type="reply", data=reply)

    media_type = _portable_media_type(adapter, native_type)
    if media_type is not None:
        media = dict(data)
        media["media_type"] = media_type
        if native_type != media_type:
            media["adapter_type"] = native_type
        source = data.get("src") or data.get("url") or data.get("file")
        if isinstance(source, str) and source:
            media["url"] = source
        if portable_children:
            media["children"] = portable_children
        return Segment(type="media", data=media)

    adapter_data: dict[str, Any] = {
        "adapter": adapter,
        "type": native_type,
        "data": data,
    }
    if portable_children:
        adapter_data["children"] = portable_children
    return Segment(type="adapter", data=adapter_data)


def _native_data(adapter: str, native_type: str, value: Any) -> dict[str, Any]:
    """Implement the native data operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        native_type: The native type value used by the operation.
        value: Value to validate, transform, or store.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_data`. It delegates to `pop`, `json_value`,
        `_portable_styles` while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, Mapping):
        raise TypeError(f"native {native_type!r} segment data must be an object")
    if adapter == "satori" and native_type == "text":
        mutable = dict(value)
        styles = mutable.pop("styles", None)
        data = json_value(mutable)
        if not isinstance(data, dict):
            raise TypeError("native segment data must serialize to an object")
        data["styles"] = _portable_styles(styles)
        return data
    data = json_value(value)
    if not isinstance(data, dict):
        raise TypeError("native segment data must serialize to an object")
    return data


def _portable_styles(value: Any) -> list[dict[str, Any]]:
    """Implement the portable styles operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `list[dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_styles`. It delegates to `items`, `append`, `int`
        while keeping intermediate state local to the owning operation.
    """
    if not isinstance(value, Mapping):
        return []
    styles: list[dict[str, Any]] = []
    for bounds, names in value.items():
        if not isinstance(bounds, tuple) or len(bounds) != 2:
            continue
        if not isinstance(names, Sequence) or isinstance(names, (str, bytes, bytearray)):
            continue
        styles.append(
            {
                "start": int(bounds[0]),
                "end": int(bounds[1]),
                "types": [str(name) for name in names],
            }
        )
    return styles


def _portable_mention(adapter: str, native_type: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """Implement the portable mention operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        native_type: The native type value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_mention`. It delegates to `pop` while keeping
        intermediate state local to the owning operation.
    """
    result = dict(data)
    if adapter == "onebot-v11":
        target = str(result.pop("qq", ""))
        if target == "all":
            result["scope"] = "all"
        elif target:
            result["user_id"] = target
    elif adapter == "onebot-v12":
        target = result.pop("user_id", None)
        if native_type == "mention_all":
            result["scope"] = "all"
        elif target is not None:
            result["user_id"] = str(target)
    else:
        target = result.pop("id", None)
        role = result.pop("role", None)
        scope = result.pop("type", None)
        if target is not None:
            result["user_id"] = str(target)
        elif role is not None:
            result["role_id"] = str(role)
        elif scope in {"all", "here"}:
            result["scope"] = scope
    return result


def _portable_reply(adapter: str, data: Mapping[str, Any]) -> dict[str, Any]:
    """Implement the portable reply operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_reply`. It delegates to `pop` while keeping
        intermediate state local to the owning operation.
    """
    result = dict(data)
    native_key = "id" if adapter in {"onebot-v11", "satori"} else "message_id"
    message_id = result.pop(native_key, None)
    if message_id is not None:
        result["message_id"] = str(message_id)
    return result


def _portable_media_type(adapter: str, native_type: str) -> str | None:
    """Implement the portable media type operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        native_type: The native type value used by the operation.

    Returns:
        The `str | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_media_type`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    if adapter == "onebot-v11":
        return {"image": "image", "record": "voice", "video": "video"}.get(native_type)
    if adapter == "onebot-v12":
        return native_type if native_type in _MEDIA_TYPES else None
    if adapter == "satori":
        return {"img": "image", "audio": "audio", "video": "video", "file": "file"}.get(native_type)
    return None


def _to_native_segment(adapter: str, segment_class: Any, segment: Segment) -> Any:
    """Implement the to native segment operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        segment_class: The segment class value used by the operation.
        segment: The segment value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_to_native_segment`. It delegates to `model_dump`, `get`,
        `_portable_children`, `pop` while keeping intermediate state local to the owning operation.
    """
    dumped = segment.model_dump(mode="json")
    dumped_data = dumped.get("data")
    if not isinstance(dumped_data, dict):
        raise AdapterContractError("segment data must serialize to an object")
    data = dumped_data
    children = _portable_children(data.pop("children", None))
    native_data: dict[Any, Any]
    if segment.type == "text":
        native_type = "text"
        native_data = dict(data)
        if adapter == "satori":
            native_data["styles"] = _native_styles(native_data.get("styles"))
    elif segment.type == "mention":
        native_type, native_data = _native_mention(adapter, data)
    elif segment.type == "reply":
        native_type, native_data = _native_reply(adapter, data)
    elif segment.type == "media":
        native_type, native_data = _native_media(adapter, data)
    else:
        native_type, native_data = _native_adapter_segment(adapter, data)

    native_segment_class = _satori_segment_class(native_type) if adapter == "satori" else segment_class
    native_segment = native_segment_class(native_type, native_data)
    if children:
        if adapter != "satori":
            raise AdapterContractError(f"adapter {adapter!r} segments cannot contain children")
        child_message = to_native_message(adapter, Message(segments=children))
        native_segment(*child_message)
    return native_segment


def _portable_children(value: Any) -> tuple[Segment, ...]:
    """Implement the portable children operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `tuple[Segment, ...]` result produced by the operation.

    Notes:
        Internal implementation detail for `_portable_children`. It delegates to `model_validate` while
        keeping intermediate state local to the owning operation.
    """
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AdapterContractError("segment children must be an array")
    try:
        return tuple(Segment.model_validate(item) for item in value)
    except ValueError as error:
        raise AdapterContractError(f"invalid child segment: {error}") from error


def _native_styles(value: Any) -> dict[tuple[int, int], list[str]]:
    """Implement the native styles operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `dict[tuple[int, int], list[str]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_styles`. It delegates to `get` while keeping
        intermediate state local to the owning operation.
    """
    if value in (None, ()):  # frozen empty JSON arrays become tuples
        return {}
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AdapterContractError("Satori text styles must be an array")
    styles: dict[tuple[int, int], list[str]] = {}
    for entry in value:
        if not isinstance(entry, Mapping):
            raise AdapterContractError("Satori text style entries must be objects")
        start = entry.get("start")
        end = entry.get("end")
        names = entry.get("types")
        if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
            raise AdapterContractError("Satori text style ranges are invalid")
        if not isinstance(names, Sequence) or isinstance(names, (str, bytes, bytearray)):
            raise AdapterContractError("Satori text style types must be an array")
        styles[(start, end)] = [str(name) for name in names]
    return styles


def _native_mention(adapter: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Implement the native mention operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `tuple[str, dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_mention`. It delegates to `pop` while keeping
        intermediate state local to the owning operation.
    """
    scope = data.pop("scope", None)
    user_id = data.pop("user_id", None)
    role_id = data.pop("role_id", None)
    if adapter == "onebot-v11":
        if role_id is not None or scope == "here":
            raise AdapterContractError("OneBot v11 does not support this mention target")
        target = "all" if scope == "all" else user_id
        if target is None:
            raise AdapterContractError("mention segments require user_id or scope")
        data["qq"] = str(target)
        return "at", data
    if adapter == "onebot-v12":
        if role_id is not None or scope == "here":
            raise AdapterContractError("OneBot v12 does not support this mention target")
        if scope == "all":
            return "mention_all", data
        if user_id is None:
            raise AdapterContractError("mention segments require user_id or scope")
        data["user_id"] = str(user_id)
        return "mention", data
    if adapter == "satori":
        if user_id is not None:
            data["id"] = str(user_id)
        elif role_id is not None:
            data["role"] = str(role_id)
        elif scope in {"all", "here"}:
            data["type"] = scope
        else:
            raise AdapterContractError("mention segments require user_id, role_id, or scope")
        return "at", data
    raise AdapterContractError(f"mentions are unsupported for adapter {adapter!r}")


def _native_reply(adapter: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Implement the native reply operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `tuple[str, dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_reply`. It delegates to `pop` while keeping
        intermediate state local to the owning operation.
    """
    message_id = data.pop("message_id", None)
    if not isinstance(message_id, str) or not message_id:
        raise AdapterContractError("reply segments require a non-empty message_id")
    if adapter == "onebot-v11":
        data["id"] = message_id
        return "reply", data
    if adapter == "onebot-v12":
        data["message_id"] = message_id
        return "reply", data
    if adapter == "satori":
        data["id"] = message_id
        return "quote", data
    raise AdapterContractError(f"replies are unsupported for adapter {adapter!r}")


def _native_media(adapter: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Implement the native media operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `tuple[str, dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_media`. It delegates to `pop`, `get` while keeping
        intermediate state local to the owning operation.
    """
    media_type = data.pop("media_type", None)
    adapter_type = data.pop("adapter_type", None)
    if media_type not in _MEDIA_TYPES:
        raise AdapterContractError(f"unsupported media_type: {media_type!r}")
    url = data.pop("url", None)
    data.pop("children", None)

    if adapter == "onebot-v11":
        native_type = (
            str(adapter_type)
            if adapter_type in {"image", "record", "video"}
            else str({"audio": "record", "voice": "record"}.get(media_type, media_type))
        )
        if native_type not in {"image", "record", "video"}:
            raise AdapterContractError(f"OneBot v11 does not support {media_type!r} media")
        if "file" not in data:
            if not isinstance(url, str) or not url:
                raise AdapterContractError("OneBot v11 media requires data.file or data.url")
            data["file"] = url
        return native_type, data

    if adapter == "onebot-v12":
        native_type = str(adapter_type) if adapter_type in _MEDIA_TYPES else str(media_type)
        if native_type not in _MEDIA_TYPES:
            raise AdapterContractError(f"OneBot v12 does not support {media_type!r} media")
        if not isinstance(data.get("file_id"), str) or not data["file_id"]:
            raise AdapterContractError("OneBot v12 media requires data.file_id")
        return native_type, data

    if adapter == "satori":
        native_type = (
            str(adapter_type)
            if adapter_type in {"img", "audio", "video", "file"}
            else str({"image": "img", "voice": "audio"}.get(media_type, media_type))
        )
        if native_type not in {"img", "audio", "video", "file"}:
            raise AdapterContractError(f"Satori does not support {media_type!r} media")
        if "src" not in data:
            if not isinstance(url, str) or not url:
                raise AdapterContractError("Satori media requires data.src or data.url")
            data["src"] = url
        return native_type, data

    raise AdapterContractError(f"media is unsupported for adapter {adapter!r}")


def _native_adapter_segment(adapter: str, data: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Implement the native adapter segment operation for the component.

    Args:
        adapter: The adapter value used by the operation.
        data: The data value used by the operation.

    Returns:
        The `tuple[str, dict[str, Any]]` result produced by the operation.

    Notes:
        Internal implementation detail for `_native_adapter_segment`. It delegates to `get`, `pop` while
        keeping intermediate state local to the owning operation.
    """
    target = data.get("adapter")
    if target is not None and target != adapter:
        raise AdapterContractError(f"adapter segment targets {target!r}, but the selected adapter is {adapter!r}")
    native_type = data.get("type")
    native_data = data.get("data")
    if not isinstance(native_type, str) or not native_type:
        raise AdapterContractError("adapter segments require a non-empty type")
    if not isinstance(native_data, Mapping):
        raise AdapterContractError("adapter segments require an object data field")
    result = dict(native_data)
    if adapter == "onebot-v11" and native_type in {"image", "record", "video"}:
        if "file" not in result and isinstance(result.get("url"), str):
            result["file"] = result.pop("url")
        if not isinstance(result.get("file"), str) or not result["file"]:
            raise AdapterContractError(f"OneBot v11 {native_type} segments require data.file or data.url")
    elif adapter == "onebot-v12" and native_type in _MEDIA_TYPES:
        if not isinstance(result.get("file_id"), str) or not result["file_id"]:
            raise AdapterContractError(f"OneBot v12 {native_type} segments require data.file_id")
    elif adapter == "satori" and native_type == "image":
        native_type = "img"
        if "src" not in result and isinstance(result.get("url"), str):
            result["src"] = result.pop("url")
    return native_type, result


def _satori_segment_class(native_type: str) -> Any:
    """Implement the satori segment class operation for the component.

    Args:
        native_type: The native type value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_satori_segment_class`. It delegates to `import_module`,
        `get` while keeping intermediate state local to the owning operation.
    """
    message_module = importlib.import_module("nonebot.adapters.satori.message")
    classes = {
        "text": message_module.Text,
        "at": message_module.At,
        "sharp": message_module.Sharp,
        "emoji": message_module.Emoji,
        "link": message_module.Link,
        "img": message_module.Image,
        "audio": message_module.Audio,
        "video": message_module.Video,
        "file": message_module.File,
        "message": message_module.RenderMessage,
        "quote": message_module.RenderMessage,
        "author": message_module.Author,
        "button": message_module.Button,
        "br": message_module.Br,
    }
    return classes.get(native_type, message_module.Custom)


def _event_raw(event: Any) -> dict[str, Any]:
    """Implement the event raw operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `dict[str, Any]` result produced by the operation.

    Notes:
        Internal implementation detail for `_event_raw`. It delegates to `model_dump`, `json_value`
        while keeping intermediate state local to the owning operation.
    """
    try:
        value = event.model_dump(mode="json")
        normalized = json_value(value)
        return normalized if isinstance(normalized, dict) else {}
    except AttributeError, TypeError, ValueError:
        return {}


def _upstream_event_id(raw: Mapping[str, Any]) -> str:
    """Implement the upstream event id operation for the component.

    Args:
        raw: The raw value used by the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_upstream_event_id`. It delegates to `get`, `strip`, `uuid4`
        while keeping intermediate state local to the owning operation.
    """
    for key in ("message_id", "event_id", "id"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return str(uuid4())


def _positive_integer_id(value: str) -> int:
    """Implement the positive integer id operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `int` result produced by the operation.

    Notes:
        Internal implementation detail for `_positive_integer_id`. It delegates to `isdecimal`, `int`
        while keeping intermediate state local to the owning operation.
    """
    if not value.isdecimal() or (parsed := int(value)) <= 0:
        raise AdapterContractError("OneBot v11 conversation IDs must be positive integers")
    return parsed


def _string_attribute(value: Any, name: str) -> str | None:
    """Implement the string attribute operation for the component.

    Args:
        value: Value to validate, transform, or store.
        name: Stable name used to identify the value.

    Returns:
        The `str | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_string_attribute`. It delegates to `getattr` while keeping
        intermediate state local to the owning operation.
    """
    attribute = getattr(value, name, None)
    if attribute is None:
        return None
    result = str(attribute)
    return result or None


def _integer_value(value: Any) -> int | None:
    """Implement the integer value operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `int | None` result produced by the operation.

    Notes:
        Internal implementation detail for `_integer_value`. It delegates to `int` while keeping
        intermediate state local to the owning operation.
    """
    try:
        return int(value)
    except TypeError, ValueError:
        return None


__all__ = [
    "AdapterContractError",
    "adapter_id",
    "json_value",
    "normalize_event",
    "send_proactive",
    "to_native_message",
]
