"""Version 7 broker business-lane JSON catalog carried by LYIP frames."""

from __future__ import annotations

from typing import Annotated, Final

from pydantic import Field, TypeAdapter

from ..lyip import LyipError, LyipFrame, LyipLane
from .routing import (
    ActionRequest,
    ActionResult,
    BridgeControlInvoke,
    BridgeControlResult,
    EventAccepted,
    EventCompleted,
    EventIngress,
    EventMessage,
    RuntimeApiInvoke,
    RuntimeApiResult,
    ToolInvoke,
    ToolResult,
)

BROKER_EVENT_INGRESS_TYPE_ID: Final = 610
BROKER_EVENT_MESSAGE_TYPE_ID: Final = 611
BROKER_EVENT_ACCEPTED_TYPE_ID: Final = 612
BROKER_EVENT_COMPLETED_TYPE_ID: Final = 613
BROKER_ACTION_REQUEST_TYPE_ID: Final = 614
BROKER_ACTION_RESULT_TYPE_ID: Final = 615
BROKER_TOOL_INVOKE_TYPE_ID: Final = 616
BROKER_TOOL_RESULT_TYPE_ID: Final = 617
BROKER_CONTROL_INVOKE_TYPE_ID: Final = 618
BROKER_CONTROL_RESULT_TYPE_ID: Final = 619
BROKER_RUNTIME_API_INVOKE_TYPE_ID: Final = 620
BROKER_RUNTIME_API_RESULT_TYPE_ID: Final = 621


class BrokerBusinessWireError(LyipError):
    """Raised when a LYIP frame does not carry a valid broker business message."""


type BrokerBusinessMessage = Annotated[
    EventIngress
    | EventMessage
    | EventAccepted
    | EventCompleted
    | ActionRequest
    | ActionResult
    | ToolInvoke
    | ToolResult
    | BridgeControlInvoke
    | BridgeControlResult
    | RuntimeApiInvoke
    | RuntimeApiResult,
    Field(discriminator="type"),
]
BROKER_BUSINESS_ADAPTER: Final[TypeAdapter[BrokerBusinessMessage]] = TypeAdapter(BrokerBusinessMessage)

_TYPE_IDS: Final[dict[type[object], int]] = {
    EventIngress: BROKER_EVENT_INGRESS_TYPE_ID,
    EventMessage: BROKER_EVENT_MESSAGE_TYPE_ID,
    EventAccepted: BROKER_EVENT_ACCEPTED_TYPE_ID,
    EventCompleted: BROKER_EVENT_COMPLETED_TYPE_ID,
    ActionRequest: BROKER_ACTION_REQUEST_TYPE_ID,
    ActionResult: BROKER_ACTION_RESULT_TYPE_ID,
    ToolInvoke: BROKER_TOOL_INVOKE_TYPE_ID,
    ToolResult: BROKER_TOOL_RESULT_TYPE_ID,
    BridgeControlInvoke: BROKER_CONTROL_INVOKE_TYPE_ID,
    BridgeControlResult: BROKER_CONTROL_RESULT_TYPE_ID,
    RuntimeApiInvoke: BROKER_RUNTIME_API_INVOKE_TYPE_ID,
    RuntimeApiResult: BROKER_RUNTIME_API_RESULT_TYPE_ID,
}
_MESSAGE_TYPES: Final[dict[int, type[object]]] = {type_id: model for model, type_id in _TYPE_IDS.items()}


def encode_business_message(
    message: BrokerBusinessMessage,
    *,
    generation: int,
    stream_id: str,
    sequence: int,
    lease_id: str,
) -> LyipFrame:
    """Encode one v7 business message without transmitting a clock deadline.

    Args:
        message: Message content associated with the operation.
        generation: Positive protocol or deployment generation.
        stream_id: Stable identifier for the stream.
        sequence: Monotonic sequence number for the stream.
        lease_id: Stable identifier for the lease.

    Returns:
        The `LyipFrame` result produced by the operation.
    """

    return LyipFrame(
        protocol=1,
        generation=generation,
        lane=LyipLane.BUSINESS,
        type_id=_TYPE_IDS[type(message)],
        stream_id=stream_id,
        sequence=sequence,
        lease_id=lease_id,
        payload=message.model_dump_json(exclude_none=True).encode("utf-8"),
    )


def decode_business_message(frame: LyipFrame) -> BrokerBusinessMessage:
    """Decode exactly one known v7 business catalog message.

    Args:
        frame: The frame value used by the operation.

    Returns:
        The `BrokerBusinessMessage` result produced by the operation.
    """

    if frame.lane is not LyipLane.BUSINESS:
        raise BrokerBusinessWireError("broker business message arrived on the wrong LYIP lane")
    if frame.type_id not in _MESSAGE_TYPES:
        raise BrokerBusinessWireError(f"unknown broker business v7 type ID: {frame.type_id}")
    try:
        message = BROKER_BUSINESS_ADAPTER.validate_json(frame.payload)
    except ValueError as error:
        raise BrokerBusinessWireError("broker business v7 payload is invalid") from error
    if _TYPE_IDS[type(message)] != frame.type_id:
        raise BrokerBusinessWireError("broker business v7 type ID does not match payload type")
    return message
