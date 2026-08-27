"""Authenticated Broker lifecycle controls used by the instance daemon."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

import zmq.asyncio

from .lyip import LyipLane, LyipOfferResult, ZmqLyipDealer
from .protocol import (
    BridgeRejected,
    BrokerLifecycleDrain,
    BrokerLifecycleFreeze,
    BrokerLifecycleStatusResult,
    BrokerLifecycleUnfreeze,
    BrokerWireMessage,
    decode_broker_message,
    encode_broker_message,
)


class BrokerLifecycleError(RuntimeError):
    """Raised when a daemon lifecycle request cannot be completed."""


class BrokerLifecycleClient:
    """Small authenticated client kept separate from read-only diagnostics."""

    def __init__(
        self,
        *,
        context: zmq.asyncio.Context,
        endpoints: Mapping[LyipLane, str],
        generation: int,
        identity: bytes,
        management_token: str,
        control_hwm: int = 100,
    ) -> None:
        """Initialize the broker lifecycle client.

        Args:
            context: Runtime or authorization context for the operation.
            endpoints: The endpoints value used by the operation.
            generation: Positive protocol or deployment generation.
            identity: The identity value used by the operation.
            management_token: The management token value used by the operation.
            control_hwm: The control hwm value used by the operation.

        Returns:
            None.
        """
        token = management_token.strip()
        if not token:
            raise ValueError("broker management token must be non-empty")
        if not identity:
            raise ValueError("broker lifecycle peer identity must be non-empty")
        self._token = token
        self._generation = generation
        self._sequence = 0
        self._dealer = ZmqLyipDealer(
            context=context,
            endpoints=dict(endpoints),
            generation=generation,
            identity=identity,
            business_hwm=1,
            control_hwm=control_hwm,
        )
        self._lock = asyncio.Lock()

    @classmethod
    def from_broker_endpoint(
        cls,
        *,
        context: zmq.asyncio.Context,
        endpoint: str,
        generation: int,
        identity: bytes,
        management_token: str,
        control_hwm: int = 100,
    ) -> BrokerLifecycleClient:
        """Create the broker lifecycle client from broker endpoint.

        Args:
            context: Runtime or authorization context for the operation.
            endpoint: Transport endpoint used for the connection.
            generation: Positive protocol or deployment generation.
            identity: The identity value used by the operation.
            management_token: The management token value used by the operation.
            control_hwm: The control hwm value used by the operation.

        Returns:
            The `BrokerLifecycleClient` result produced by the operation.
        """
        parsed = urlsplit(endpoint)
        if parsed.scheme != "tcp" or parsed.hostname is None or parsed.port is None or parsed.port >= 65_535:
            raise ValueError("broker lifecycle client requires a TCP endpoint with a free business port")
        host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
        endpoints = {
            LyipLane.CONTROL: endpoint,
            LyipLane.BUSINESS: urlunsplit((parsed.scheme, f"{host}:{parsed.port + 1}", "", "", "")),
        }
        return cls(
            context=context,
            endpoints=endpoints,
            generation=generation,
            identity=identity,
            management_token=management_token,
            control_hwm=control_hwm,
        )

    async def freeze(self, reason: str = "instance update") -> BrokerLifecycleStatusResult:
        """Freeze the broker lifecycle client operation.

        Args:
            reason: The reason value used by the operation.

        Returns:
            The `BrokerLifecycleStatusResult` result produced by the operation.
        """
        response = await self._request(BrokerLifecycleFreeze(token=self._token, reason=reason))
        return self._expect_status(response)

    async def drain(self) -> BrokerLifecycleStatusResult:
        """Implement the drain operation for the broker lifecycle client.

        Returns:
            The `BrokerLifecycleStatusResult` result produced by the operation.
        """
        response = await self._request(BrokerLifecycleDrain(token=self._token))
        return self._expect_status(response)

    async def unfreeze(self) -> BrokerLifecycleStatusResult:
        """Implement the unfreeze operation for the broker lifecycle client.

        Returns:
            The `BrokerLifecycleStatusResult` result produced by the operation.
        """
        response = await self._request(BrokerLifecycleUnfreeze(token=self._token))
        return self._expect_status(response)

    def close(self) -> None:
        """Close the broker lifecycle client and release its owned resources.

        Returns:
            None.
        """
        self._dealer.close()

    @staticmethod
    def _expect_status(response: BrokerWireMessage) -> BrokerLifecycleStatusResult:
        """Implement the expect status operation for the broker lifecycle client.

        Args:
            response: The response value used by the operation.

        Returns:
            The `BrokerLifecycleStatusResult` result produced by the operation.

        Notes:
            Internal implementation detail for `BrokerLifecycleClient._expect_status`. It performs the local
            state transition directly and is not a stable extension boundary.
        """
        if not isinstance(response, BrokerLifecycleStatusResult):
            raise BrokerLifecycleError("broker returned an unexpected lifecycle response")
        return response

    async def _request(
        self,
        message: BrokerLifecycleFreeze | BrokerLifecycleDrain | BrokerLifecycleUnfreeze,
    ) -> BrokerWireMessage:
        """Request the broker lifecycle client operation.

        Args:
            message: Message content associated with the operation.

        Returns:
            The `BrokerWireMessage` result produced by the operation.

        Notes:
            Internal implementation detail for `BrokerLifecycleClient._request`. It delegates to
            `encode_broker_message`, `offer`, `decode_broker_message`, `receive` while keeping intermediate
            state local to the owning operation.
        """
        async with self._lock:
            frame = encode_broker_message(
                message,
                generation=self._generation,
                stream_id="broker:lifecycle:control",
                sequence=self._sequence,
                lease_id="broker-lifecycle",
            )
            if await self._dealer.offer(frame) is not LyipOfferResult.ACCEPTED:
                raise BrokerLifecycleError("broker lifecycle control message could not be queued")
            self._sequence += 1
            response = decode_broker_message(await self._dealer.receive(LyipLane.CONTROL))
        if isinstance(response, BridgeRejected):
            raise BrokerLifecycleError(f"broker lifecycle rejected: {response.code}")
        return response


__all__ = ["BrokerLifecycleClient", "BrokerLifecycleError"]
