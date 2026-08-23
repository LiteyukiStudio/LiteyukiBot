"""Authenticated loopback HTTP transport for the packaged LiteyukiBot WebUI."""

from __future__ import annotations

import asyncio
import hmac
import importlib
import inspect
import json
import secrets
import time
from collections.abc import AsyncIterable, Awaitable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import quote, urlsplit

try:
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
except ModuleNotFoundError:
    FastAPI = None  # type: ignore[misc,assignment]
    Request = Any  # type: ignore[misc,assignment]
    FileResponse = JSONResponse = Response = StreamingResponse = Any  # type: ignore[misc,assignment]


type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | Mapping[str, "JsonValue"]
type JsonObject = Mapping[str, JsonValue]
type MaybeAwaitable[T] = T | Awaitable[T]

_COOKIE_NAME = "liteyuki_webui_session"
_EVENT_TYPES = frozenset({"snapshot", "ledger_append", "operation", "event_delivery", "heartbeat", "reset"})
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_MAX_EVENT_REPLAY = 4096
_SSE_REAUTHORIZATION_SECONDS = 15.0
_MAX_EVENT_DELIVERY_FILTER_LENGTH = 256
_MAX_EVENT_DELIVERY_ID_LENGTH = 256
_MAX_PLUGIN_FILTER_LENGTH = 128
_MAX_PLUGIN_ID_LENGTH = 256
_MAX_PLUGIN_PAGE_SIZE = 100


class WebUiUnavailableError(RuntimeError):
    """Raised when the optional WebUI server dependencies are unavailable."""


class WebUiServiceError(RuntimeError):
    """A bridge error whose stable code may be returned to the browser."""

    def __init__(self, code: str, status_code: int = 400) -> None:
        """Initialize the web ui service error.

        Args:
            code: The code value used by the operation.
            status_code: The status code value used by the operation.

        Returns:
            None.
        """
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class WebUiPrincipal:
    """Authenticated local administrator identity returned when a ticket is redeemed."""

    subject: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        """Validate and normalize the web ui principal after initialization.

        Returns:
            None.
        """
        if not self.subject:
            raise ValueError("webui principal subject must not be empty")


@dataclass(frozen=True, slots=True)
class WebUiEvent:
    """A redacted daemon event delivered to a browser over SSE."""

    event: str
    data: JsonObject
    identifier: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize the web ui event after initialization.

        Returns:
            None.
        """
        if self.event not in _EVENT_TYPES:
            raise ValueError(f"unsupported webui event type: {self.event}")
        if self.identifier is not None and not self.identifier:
            raise ValueError("webui event identifier must not be empty")


@dataclass(frozen=True, slots=True)
class WebUiEventReplay:
    """The bounded replay result supplied by the daemon-owned event history."""

    events: tuple[WebUiEvent, ...]
    reset: bool = False

    def __post_init__(self) -> None:
        """Validate and normalize the web ui event replay after initialization.

        Returns:
            None.
        """
        if len(self.events) > _MAX_EVENT_REPLAY:
            raise ValueError("webui event replay exceeds the protocol limit")


class WebUiBridge(Protocol):
    """Daemon-owned data and authorization boundary used by the WebUI transport."""

    def issue_ticket(self) -> MaybeAwaitable[str]:
        """Implement the issue ticket operation for the web ui bridge.

        Returns:
            The `MaybeAwaitable[str]` result produced by the operation.
        """
        ...

    def redeem_ticket(self, ticket: str) -> MaybeAwaitable[WebUiPrincipal | None]:
        """Redeem ticket.

        Args:
            ticket: The ticket value used by the operation.

        Returns:
            The `MaybeAwaitable[WebUiPrincipal | None]` result produced by the operation.
        """
        ...

    def authorize_session(self, principal: WebUiPrincipal) -> MaybeAwaitable[bool]:
        """Authorize session.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `MaybeAwaitable[bool]` result produced by the operation.
        """
        ...

    def bootstrap(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Implement the bootstrap operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def presentation(self, principal: WebUiPrincipal, locale: str | None) -> MaybeAwaitable[JsonObject]:
        """Implement the presentation operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            locale: The locale value used by the operation.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def snapshot(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Return an immutable snapshot of the web ui bridge state.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The requested `MaybeAwaitable[JsonObject]` value.
        """
        ...

    def operation_catalog(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Implement the operation catalog operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def submit_operation(self, principal: WebUiPrincipal, request: JsonObject) -> MaybeAwaitable[JsonObject]:
        """Implement the submit operation operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            request: Validated request object to process.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def operation(self, principal: WebUiPrincipal, operation_id: str) -> MaybeAwaitable[JsonObject | None]:
        """Implement the operation operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            operation_id: Stable identifier for the operation.

        Returns:
            The `MaybeAwaitable[JsonObject | None]` result produced by the operation.
        """
        ...

    def ledger(
        self, principal: WebUiPrincipal, cursor: str | None, limit: int
    ) -> MaybeAwaitable[JsonObject]:
        """Implement the ledger operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def audit(self, principal: WebUiPrincipal, cursor: str | None, limit: int) -> MaybeAwaitable[JsonObject]:
        """Implement the audit operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def plugin_surfaces(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Implement the plugin surfaces operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def plugin_discovery(
        self,
        principal: WebUiPrincipal,
        query: str,
        source_id: str | None,
        runtime_kind: str | None,
        status: str | None,
        refresh: bool,
        cursor: str | None,
        limit: int,
    ) -> MaybeAwaitable[JsonObject]:
        """Return bounded, server-side plugin discovery results."""
        ...

    def plugin_targets(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Return configured managed plugin targets and generation summaries."""
        ...

    def plugin_preview(
        self,
        principal: WebUiPrincipal,
        bundle_id: str,
        source_id: str,
        target_id: str,
    ) -> MaybeAwaitable[JsonObject]:
        """Return digest-bound metadata for one target-specific install preview."""
        ...

    def lyf_resources(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]:
        """Implement the lyf resources operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def event_deliveries(
        self,
        principal: WebUiPrincipal,
        filters: Mapping[str, str],
        cursor: str | None,
        limit: int,
    ) -> MaybeAwaitable[JsonObject]:
        """Implement the event deliveries operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            filters: Validated filters applied to the result set.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `MaybeAwaitable[JsonObject]` result produced by the operation.
        """
        ...

    def event_delivery(self, principal: WebUiPrincipal, event_id: str) -> MaybeAwaitable[JsonObject | None]:
        """Implement the event delivery operation for the web ui bridge.

        Args:
            principal: Authenticated principal requesting the operation.
            event_id: Stable event identifier.

        Returns:
            The `MaybeAwaitable[JsonObject | None]` result produced by the operation.
        """
        ...

    def replay_events(
        self, principal: WebUiPrincipal, after_id: str | None, limit: int
    ) -> MaybeAwaitable[WebUiEventReplay]:
        """Replay events.

        Args:
            principal: Authenticated principal requesting the operation.
            after_id: Last observed event identifier, or `None` to start at the current boundary.
            limit: Maximum number of records to return.

        Returns:
            The `MaybeAwaitable[WebUiEventReplay]` result produced by the operation.
        """
        ...

    def stream_events(self, principal: WebUiPrincipal, after_id: str | None) -> AsyncIterable[WebUiEvent]:
        """Stream events.

        Args:
            principal: Authenticated principal requesting the operation.
            after_id: Last observed event identifier, or `None` to start at the current boundary.

        Returns:
            The `AsyncIterable[WebUiEvent]` result produced by the operation.
        """
        ...


@dataclass(slots=True)
class _Session:
    """Represent the session contract."""
    principal: WebUiPrincipal
    csrf_token: str
    created_at: float
    last_seen_at: float


class _SessionStore:
    """Represent the session store contract."""
    def __init__(self, *, idle_seconds: int, maximum_seconds: int) -> None:
        """Initialize the session store.

        Args:
            idle_seconds: Configured idle duration, in seconds.
            maximum_seconds: Configured maximum duration, in seconds.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_SessionStore.__init__`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        if idle_seconds < 60 or maximum_seconds < idle_seconds:
            raise ValueError("invalid WebUI session lifetime")
        self._idle_seconds = idle_seconds
        self._maximum_seconds = maximum_seconds
        self._sessions: dict[str, _Session] = {}

    def create(self, principal: WebUiPrincipal) -> tuple[str, _Session]:
        """Create the session store operation.

        Args:
            principal: Authenticated principal requesting the operation.

        Returns:
            The `tuple[str, _Session]` result produced by the operation.

        Notes:
            Internal implementation detail for `_SessionStore.create`. It delegates to `monotonic`,
            `_Session`, `token_urlsafe` while keeping intermediate state local to the owning operation.
        """
        now = time.monotonic()
        session = _Session(principal, secrets.token_urlsafe(32), now, now)
        identifier = secrets.token_urlsafe(32)
        self._sessions[identifier] = session
        return identifier, session

    def get(self, identifier: str | None, *, touch: bool = True) -> _Session | None:
        """Return the session store operation.

        Args:
            identifier: The identifier value used by the operation.
            touch: The touch value used by the operation.

        Returns:
            The `_Session | None` result produced by the operation.

        Notes:
            Internal implementation detail for `_SessionStore.get`. It delegates to `get`, `monotonic`,
            `pop` while keeping intermediate state local to the owning operation.
        """
        if identifier is None:
            return None
        session = self._sessions.get(identifier)
        if session is None:
            return None
        now = time.monotonic()
        if now - session.last_seen_at > self._idle_seconds or now - session.created_at > self._maximum_seconds:
            self._sessions.pop(identifier, None)
            return None
        if touch:
            session.last_seen_at = now
        return session

    def remove(self, identifier: str | None) -> None:
        """Remove the session store operation.

        Args:
            identifier: The identifier value used by the operation.

        Returns:
            None.

        Notes:
            Internal implementation detail for `_SessionStore.remove`. It delegates to `pop` while keeping
            intermediate state local to the owning operation.
        """
        if identifier is not None:
            self._sessions.pop(identifier, None)


async def _await[T](value: MaybeAwaitable[T]) -> T:
    """Implement the await operation for the component.

    Args:
        value: Value to validate, transform, or store.

    Returns:
        The `T` result produced by the operation.

    Notes:
        Internal implementation detail for `_await`. It delegates to `isawaitable`, `cast` while keeping
        intermediate state local to the owning operation.
    """
    if inspect.isawaitable(value):
        return await cast(Awaitable[T], value)
    return value


def _error(code: str, status_code: int) -> Any:
    """Implement the error operation for the component.

    Args:
        code: The code value used by the operation.
        status_code: The status code value used by the operation.

    Returns:
        The `Any` result produced by the operation.

    Notes:
        Internal implementation detail for `_error`. It performs the local state transition directly and
        is not a stable extension boundary.
    """
    return JSONResponse(status_code=status_code, content={"error": {"code": code}})


def _load_web_dependencies() -> None:
    """Load web dependencies.

    Returns:
        None.

    Notes:
        Internal implementation detail for `_load_web_dependencies`. It performs the local state
        transition directly and is not a stable extension boundary.
    """
    if FastAPI is None:
        raise WebUiUnavailableError(
            "WebUI support is not installed; install `liteyukibot-v7[webui]` or `liteyukibot-v7-webui[server]`."
        )


def _asset_directory(path: Path | None) -> Path:
    """Implement the asset directory operation for the component.

    Args:
        path: Filesystem or logical resource path.

    Returns:
        The `Path` result produced by the operation.

    Notes:
        Internal implementation detail for `_asset_directory`. It delegates to `static_assets`,
        `is_dir`, `resolve` while keeping intermediate state local to the owning operation.
    """
    if path is None:
        from . import static_assets

        directory = Path(str(static_assets()))
    else:
        directory = path
    if not directory.is_dir():
        raise WebUiUnavailableError("WebUI static assets are not installed.")
    return directory.resolve()


def _valid_host(host: str) -> bool:
    """Implement the valid host operation for the component.

    Args:
        host: The host value used by the operation.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_valid_host`. It delegates to `lower`, `rsplit`,
        `startswith`, `split` while keeping intermediate state local to the owning operation.
    """
    candidate = host.rsplit("@", 1)[-1].lower()
    if candidate.startswith("["):
        name = candidate.split("]", 1)[0] + "]"
    else:
        name = candidate.split(":", 1)[0]
    return name in {"127.0.0.1", "localhost", "[::1]"}


def _same_origin(request: Request, origin: str) -> bool:
    """Implement the same origin operation for the component.

    Args:
        request: Validated request object to process.
        origin: The origin value used by the operation.

    Returns:
        Whether the requested condition is satisfied.

    Notes:
        Internal implementation detail for `_same_origin`. It delegates to `urlsplit`, `lower`, `get`
        while keeping intermediate state local to the owning operation.
    """
    parsed = urlsplit(origin)
    if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    return parsed.scheme == request.url.scheme and parsed.netloc.lower() == request.headers.get("host", "").lower()


def _sse(event: WebUiEvent) -> str:
    """Implement the sse operation for the component.

    Args:
        event: Event associated with the operation.

    Returns:
        The `str` result produced by the operation.

    Notes:
        Internal implementation detail for `_sse`. It delegates to `append`, `dumps`, `join` while
        keeping intermediate state local to the owning operation.
    """
    lines: list[str] = []
    if event.identifier is not None:
        lines.append(f"id: {event.identifier}")
    lines.append(f"event: {event.event}")
    lines.append(f"data: {json.dumps(dict(event.data), separators=(',', ':'), ensure_ascii=True)}")
    return "\n".join(lines) + "\n\n"


def create_app(
    bridge: WebUiBridge,
    *,
    asset_directory: Path | None = None,
    session_idle_seconds: int = 1800,
    session_max_seconds: int = 28800,
) -> Any:
    """Create an authenticated, loopback-only ASGI application around a daemon bridge.

    Args:
        bridge: The bridge value used by the operation.
        asset_directory: The asset directory value used by the operation.
        session_idle_seconds: Configured session idle duration, in seconds.
        session_max_seconds: Configured session max duration, in seconds.

    Returns:
        Values yielded by the operation.
    """
    _load_web_dependencies()
    assets = _asset_directory(asset_directory)
    sessions = _SessionStore(idle_seconds=session_idle_seconds, maximum_seconds=session_max_seconds)
    app = FastAPI(title="LiteyukiBot WebUI", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def loopback_policy(request: Request, call_next: Any) -> Any:
        """Implement the loopback policy operation for the create app.

        Args:
            request: Validated request object to process.
            call_next: The call next value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.loopback_policy`. It delegates to `get`,
            `_valid_host`, `_error`, `_same_origin` while keeping intermediate state local to the owning
            operation.
        """
        host = request.headers.get("host", "")
        if not _valid_host(host):
            return _error("webui.invalid_host", 400)
        origin = request.headers.get("origin")
        if origin is not None and not _same_origin(request, origin):
            return _error("webui.invalid_origin", 403)
        if request.method in _UNSAFE_METHODS and origin is None:
            return _error("webui.origin_required", 403)
        return await call_next(request)

    async def authenticated(request: Request, *, csrf: bool = False, touch: bool = True) -> _Session:
        """Implement the authenticated operation for the create app.

        Args:
            request: Validated request object to process.
            csrf: The csrf value used by the operation.
            touch: The touch value used by the operation.

        Returns:
            The `_Session` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.authenticated`. It delegates to `get`,
            `compare_digest`, `_await`, `authorize_session` while keeping intermediate state local to the
            owning operation.
        """
        identifier = request.cookies.get(_COOKIE_NAME)
        session = sessions.get(identifier, touch=touch)
        if session is None:
            raise WebUiServiceError("webui.session_required", 401)
        if csrf and not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session.csrf_token):
            raise WebUiServiceError("webui.csrf_required", 403)
        try:
            authorized = await _await(bridge.authorize_session(session.principal))
        except WebUiServiceError:
            raise
        except Exception as error:
            raise WebUiServiceError("webui.authorization_unavailable", 503) from error
        if not authorized:
            sessions.remove(identifier)
            raise WebUiServiceError("webui.session_invalid", 401)
        return session

    async def invoke[T](value: MaybeAwaitable[T]) -> T:
        """Invoke the create app operation.

        Args:
            value: Value to validate, transform, or store.

        Returns:
            The `T` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.invoke`. It delegates to `_await` while keeping
            intermediate state local to the owning operation.
        """
        try:
            return await _await(value)
        except WebUiServiceError:
            raise
        except Exception as error:
            raise WebUiServiceError("webui.bridge_unavailable", 503) from error

    @app.exception_handler(WebUiServiceError)
    async def service_error(_request: Request, error: WebUiServiceError) -> Any:
        """Implement the service error operation for the create app.

        Args:
            _request: The request value used by the operation.
            error: The error value used by the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.service_error`. It delegates to `_error` while
            keeping intermediate state local to the owning operation.
        """
        return _error(error.code, error.status_code)

    @app.post("/api/v1/session")
    async def redeem_ticket(request: Request) -> Any:
        """Redeem ticket.

        Args:
            request: Validated request object to process.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.redeem_ticket`. It delegates to `json`, `invoke`,
            `redeem_ticket`, `create` while keeping intermediate state local to the owning operation.
        """
        try:
            payload = await request.json()
        except json.JSONDecodeError as error:
            raise WebUiServiceError("webui.invalid_request", 400) from error
        if not isinstance(payload, dict) or set(payload) != {"ticket"} or not isinstance(payload["ticket"], str):
            raise WebUiServiceError("webui.invalid_request", 400)
        principal = await invoke(bridge.redeem_ticket(payload["ticket"]))
        if principal is None:
            raise WebUiServiceError("webui.ticket_invalid", 401)
        identifier, session = sessions.create(principal)
        response = JSONResponse({"csrf_token": session.csrf_token})
        response.set_cookie(_COOKIE_NAME, identifier, httponly=True, samesite="strict", secure=False, path="/")
        return response

    @app.get("/api/v1/session")
    async def session(request: Request) -> Any:
        """Implement the session operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.session`. It delegates to `authenticated` while
            keeping intermediate state local to the owning operation.
        """
        active = await authenticated(request)
        return {"csrf_token": active.csrf_token}

    @app.delete("/api/v1/session")
    async def close_session(request: Request) -> Any:
        """Close session.

        Args:
            request: Validated request object to process.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.close_session`. It delegates to `authenticated`,
            `remove`, `get`, `delete_cookie` while keeping intermediate state local to the owning operation.
        """
        await authenticated(request, csrf=True)
        sessions.remove(request.cookies.get(_COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(_COOKIE_NAME, path="/")
        return response

    @app.get("/api/v1/bootstrap")
    async def bootstrap(request: Request) -> JsonObject:
        """Implement the bootstrap operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.bootstrap`. It delegates to `authenticated`,
            `invoke`, `bootstrap` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        return await invoke(bridge.bootstrap(session.principal))

    @app.get("/api/v1/presentation")
    async def presentation(request: Request, locale: str | None = None) -> JsonObject:
        """Implement the presentation operation for the create app.

        Args:
            request: Validated request object to process.
            locale: The locale value used by the operation.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.presentation`. It delegates to `authenticated`,
            `invoke`, `presentation` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        value = dict(await invoke(bridge.presentation(session.principal, locale)))
        from . import __version__

        value["webui_version"] = __version__
        return value

    @app.get("/api/v1/snapshot")
    async def snapshot(request: Request) -> JsonObject:
        """Return an immutable snapshot of the create app state.

        Args:
            request: Validated request object to process.

        Returns:
            The requested `JsonObject` value.

        Notes:
            Internal implementation detail for `create_app.snapshot`. It delegates to `authenticated`,
            `invoke`, `snapshot` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        return await invoke(bridge.snapshot(session.principal))

    @app.get("/api/v1/operations/catalog")
    async def operation_catalog(request: Request) -> JsonObject:
        """Implement the operation catalog operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.operation_catalog`. It delegates to
            `authenticated`, `invoke`, `operation_catalog` while keeping intermediate state local to the
            owning operation.
        """
        session = await authenticated(request)
        return await invoke(bridge.operation_catalog(session.principal))

    @app.post("/api/v1/operations")
    async def submit_operation(request: Request) -> JsonObject:
        """Implement the submit operation operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.submit_operation`. It delegates to
            `authenticated`, `json`, `invoke`, `submit_operation` while keeping intermediate state local to
            the owning operation.
        """
        session = await authenticated(request, csrf=True)
        try:
            payload = await request.json()
        except json.JSONDecodeError as error:
            raise WebUiServiceError("webui.invalid_request", 400) from error
        if not isinstance(payload, dict):
            raise WebUiServiceError("webui.invalid_request", 400)
        return await invoke(bridge.submit_operation(session.principal, cast(JsonObject, payload)))

    @app.get("/api/v1/operations/{operation_id}")
    async def operation(request: Request, operation_id: str) -> Any:
        """Implement the operation operation for the create app.

        Args:
            request: Validated request object to process.
            operation_id: Stable identifier for the operation.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.operation`. It delegates to `authenticated`,
            `invoke`, `operation` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        record = await invoke(bridge.operation(session.principal, operation_id))
        if record is None:
            raise WebUiServiceError("webui.operation_not_found", 404)
        return record

    @app.get("/api/v1/ledger")
    async def ledger(request: Request, cursor: str | None = None, limit: int = 100) -> JsonObject:
        """Implement the ledger operation for the create app.

        Args:
            request: Validated request object to process.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.ledger`. It delegates to `authenticated`,
            `invoke`, `ledger` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        return await invoke(bridge.ledger(session.principal, cursor, limit))

    @app.get("/api/v1/audit")
    async def audit(request: Request, cursor: str | None = None, limit: int = 100) -> JsonObject:
        """Implement the audit operation for the create app.

        Args:
            request: Validated request object to process.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.audit`. It delegates to `authenticated`,
            `invoke`, `audit` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        return await invoke(bridge.audit(session.principal, cursor, limit))

    @app.get("/api/v1/plugins/surfaces")
    async def plugin_surfaces(request: Request) -> JsonObject:
        """Implement the plugin surfaces operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.plugin_surfaces`. It delegates to
            `authenticated`, `invoke`, `plugin_surfaces` while keeping intermediate state local to the
            owning operation.
        """
        session = await authenticated(request)
        return await invoke(bridge.plugin_surfaces(session.principal))

    @app.get("/api/v1/plugins/discovery")
    async def plugin_discovery(
        request: Request,
        query: str = "",
        source_id: str | None = None,
        runtime_kind: str | None = None,
        status: str | None = None,
        refresh: bool = False,
        cursor: str | None = None,
        limit: int = 50,
    ) -> JsonObject:
        """Return bounded server-side plugin discovery results."""
        session = await authenticated(request)
        if len(query) > _MAX_PLUGIN_FILTER_LENGTH:
            raise WebUiServiceError("webui.invalid_plugin_filter", 400)
        for value in (source_id, runtime_kind, status):
            if value is not None and (not value or len(value) > _MAX_PLUGIN_FILTER_LENGTH):
                raise WebUiServiceError("webui.invalid_plugin_filter", 400)
        if status is not None and status not in {"active", "yanked", "all"}:
            raise WebUiServiceError("webui.invalid_plugin_status", 400)
        if cursor is not None and (not cursor.isdigit() or len(cursor) > 12):
            raise WebUiServiceError("webui.invalid_plugin_cursor", 400)
        if not 1 <= limit <= _MAX_PLUGIN_PAGE_SIZE:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        return await invoke(
            bridge.plugin_discovery(
                session.principal,
                query,
                source_id,
                runtime_kind,
                status,
                refresh,
                cursor,
                limit,
            )
        )

    @app.get("/api/v1/plugins/targets")
    async def plugin_targets(request: Request) -> JsonObject:
        """Return configured managed plugin targets."""
        session = await authenticated(request)
        return await invoke(bridge.plugin_targets(session.principal))

    @app.get("/api/v1/plugins/preview/{bundle_id}")
    async def plugin_preview(
        request: Request,
        bundle_id: str,
        source_id: str | None = None,
        target_id: str | None = None,
    ) -> JsonObject:
        """Return a target-specific, digest-bound plugin install preview."""
        session = await authenticated(request)
        if not bundle_id or len(bundle_id) > _MAX_PLUGIN_ID_LENGTH:
            raise WebUiServiceError("webui.invalid_plugin_id", 400)
        if source_id is None or not source_id or len(source_id) > _MAX_PLUGIN_FILTER_LENGTH:
            raise WebUiServiceError("webui.invalid_plugin_source", 400)
        if target_id is None or not target_id or len(target_id) > _MAX_PLUGIN_FILTER_LENGTH:
            raise WebUiServiceError("webui.plugin_target_required", 400)
        return await invoke(bridge.plugin_preview(session.principal, bundle_id, source_id, target_id))

    @app.get("/api/v1/lyf/resources")
    async def lyf_resources(request: Request) -> JsonObject:
        """Implement the lyf resources operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.lyf_resources`. It delegates to `authenticated`,
            `invoke`, `lyf_resources` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        return await invoke(bridge.lyf_resources(session.principal))

    @app.get("/api/v1/event-deliveries")
    async def event_deliveries(
        request: Request,
        cursor: str | None = None,
        limit: int = 100,
        state: str | None = None,
        topic: str | None = None,
        source: str | None = None,
        target: str | None = None,
        failure: str | None = None,
    ) -> JsonObject:
        """Implement the event deliveries operation for the create app.

        Args:
            request: Validated request object to process.
            cursor: Opaque pagination cursor, or `None` for the first page.
            limit: Maximum number of records to return.
            state: The state value used by the operation.
            topic: The topic value used by the operation.
            source: Source value or location to process.
            target: Target value or location for the operation.
            failure: The failure value used by the operation.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.event_deliveries`. It delegates to
            `authenticated`, `items`, `any`, `values` while keeping intermediate state local to the owning
            operation.
        """
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        filters = {
            name: value
            for name, value in {
                "state": state,
                "topic": topic,
                "source": source,
                "target": target,
                "failure": failure,
            }.items()
            if value is not None
        }
        if any(not value or len(value) > _MAX_EVENT_DELIVERY_FILTER_LENGTH for value in filters.values()):
            raise WebUiServiceError("webui.invalid_event_delivery_filter", 400)
        return await invoke(bridge.event_deliveries(session.principal, filters, cursor, limit))

    @app.get("/api/v1/event-deliveries/{event_id}")
    async def event_delivery(request: Request, event_id: str) -> JsonObject:
        """Implement the event delivery operation for the create app.

        Args:
            request: Validated request object to process.
            event_id: Stable event identifier.

        Returns:
            The `JsonObject` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.event_delivery`. It delegates to `authenticated`,
            `invoke`, `event_delivery` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        if not event_id or len(event_id) > _MAX_EVENT_DELIVERY_ID_LENGTH:
            raise WebUiServiceError("webui.invalid_event_delivery_id", 400)
        record = await invoke(bridge.event_delivery(session.principal, event_id))
        if record is None:
            raise WebUiServiceError("webui.event_delivery_not_found", 404)
        return record

    @app.get("/api/v1/events")
    async def events(request: Request) -> Any:
        """Implement the events operation for the create app.

        Args:
            request: Validated request object to process.

        Returns:
            Values yielded by the operation.

        Notes:
            Internal implementation detail for `create_app.events`. It delegates to `authenticated`, `get`,
            `invoke`, `replay_events` while keeping intermediate state local to the owning operation.
        """
        session = await authenticated(request)
        after_id = request.headers.get("last-event-id")
        replay = await invoke(bridge.replay_events(session.principal, after_id, _MAX_EVENT_REPLAY))

        async def stream() -> AsyncIterable[str]:
            """Stream the events operation.

            Returns:
                Values yielded by the operation.

            Notes:
                Internal implementation detail for `create_app.events.stream`. It delegates to `monotonic`,
                `_sse`, `stream_events`, `reauthorize_if_due` while keeping intermediate state local to the
                owning operation.
            """
            next_reauthorization_at = time.monotonic() + _SSE_REAUTHORIZATION_SECONDS

            async def reauthorize_if_due() -> None:
                """Implement the reauthorize if due operation for the stream.

                Returns:
                    None.

                Notes:
                    Internal implementation detail for `create_app.events.stream.reauthorize_if_due`. It delegates
                    to `monotonic`, `authenticated` while keeping intermediate state local to the owning operation.
                """
                nonlocal next_reauthorization_at
                if time.monotonic() >= next_reauthorization_at:
                    await authenticated(request, touch=False)
                    next_reauthorization_at = time.monotonic() + _SSE_REAUTHORIZATION_SECONDS

            if replay.reset:
                yield _sse(WebUiEvent("reset", {"reason": "replay_unavailable"}))
                return
            for event in replay.events:
                yield _sse(event)
            try:
                async for event in bridge.stream_events(session.principal, after_id):
                    await reauthorize_if_due()
                    yield _sse(event)
            except WebUiServiceError as error:
                yield _sse(WebUiEvent("reset", {"reason": error.code}))
            except Exception:
                yield _sse(WebUiEvent("reset", {"reason": "bridge_unavailable"}))

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str) -> Any:
        """Implement the frontend operation for the create app.

        Args:
            path: Filesystem or logical resource path.

        Returns:
            The `Any` result produced by the operation.

        Notes:
            Internal implementation detail for `create_app.frontend`. It delegates to `resolve`,
            `is_relative_to`, `is_file` while keeping intermediate state local to the owning operation.
        """
        candidate = (assets / path).resolve()
        if path and candidate.is_relative_to(assets) and candidate.is_file():
            return FileResponse(candidate)
        index = assets / "index.html"
        if index.is_file():
            return FileResponse(index)
        raise WebUiServiceError("webui.assets_unavailable", 503)

    return app


class WebUiServer:
    """Optional Uvicorn lifecycle wrapper for a loopback-only WebUI application."""

    def __init__(
        self,
        bridge: WebUiBridge,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        asset_directory: Path | None = None,
        session_idle_seconds: int = 1800,
        session_max_seconds: int = 28800,
    ) -> None:
        """Initialize the web ui server.

        Args:
            bridge: The bridge value used by the operation.
            host: The host value used by the operation.
            port: The port value used by the operation.
            asset_directory: The asset directory value used by the operation.
            session_idle_seconds: Configured session idle duration, in seconds.
            session_max_seconds: Configured session max duration, in seconds.

        Returns:
            None.
        """
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("WebUI server must bind a loopback address")
        if not 0 <= port <= 65535:
            raise ValueError("WebUI port is outside the valid range")
        self.host = host
        self.port = port
        self._bridge = bridge
        self.app = create_app(
            bridge,
            asset_directory=asset_directory,
            session_idle_seconds=session_idle_seconds,
            session_max_seconds=session_max_seconds,
        )
        self._server: Any = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the web ui server.

        Returns:
            None.
        """
        try:
            uvicorn = importlib.import_module("uvicorn")
        except ModuleNotFoundError as error:
            raise WebUiUnavailableError(
                "WebUI server support is not installed; install `liteyukibot-v7-webui[server]`."
            ) from error
        config = uvicorn.Config(self.app, host=self.host, port=self.port, access_log=False, log_config=None)
        self._server = uvicorn.Server(config)
        self._task = asyncio.create_task(self._server.serve(), name="liteyukibot-webui")
        async with asyncio.timeout(10):
            while not self._server.started:
                if self._task.done():
                    await self._task
                    raise RuntimeError("WebUI server stopped during startup")
                await asyncio.sleep(0.01)
        if self.port == 0:
            servers = getattr(self._server, "servers", ())
            if servers and servers[0].sockets:
                self.port = int(servers[0].sockets[0].getsockname()[1])

    async def open(self) -> str:
        """Start the service and return a fragment handoff URL for a fresh daemon ticket.

        Returns:
            The `str` result produced by the operation.
        """
        if self._server is None:
            await self.start()
        ticket = await _await(self._bridge.issue_ticket())
        if not ticket:
            raise WebUiServiceError("webui.ticket_unavailable", 503)
        return self.handoff_url(ticket)

    def handoff_url(self, ticket: str) -> str:
        """Build a browser-only ticket handoff URL without placing it in an HTTP request.

        Args:
            ticket: The ticket value used by the operation.

        Returns:
            The `str` result produced by the operation.
        """
        if not ticket:
            raise ValueError("WebUI ticket must not be empty")
        return f"http://{self._url_host()}:{self.port}/#ticket={quote(ticket, safe='')}"

    def status(self) -> JsonObject:
        """Return a redacted, JSON-safe server lifecycle snapshot for daemon control.

        Returns:
            The requested `JsonObject` value.
        """
        state = "running" if self._server is not None and self._server.started else "stopped"
        return {"state": state, "host": self.host, "port": self.port}

    async def stop(self) -> None:
        """Stop the web ui server and release its owned resources.

        Returns:
            None.
        """
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
        self._server = None
        self._task = None

    def _url_host(self) -> str:
        """Implement the url host operation for the web ui server.

        Returns:
            The `str` result produced by the operation.

        Notes:
            Internal implementation detail for `WebUiServer._url_host`. It performs the local state
            transition directly and is not a stable extension boundary.
        """
        return f"[{self.host}]" if self.host == "::1" else self.host


__all__ = [
    "JsonObject",
    "JsonValue",
    "WebUiBridge",
    "WebUiEvent",
    "WebUiEventReplay",
    "WebUiPrincipal",
    "WebUiServer",
    "WebUiServiceError",
    "WebUiUnavailableError",
    "create_app",
]
