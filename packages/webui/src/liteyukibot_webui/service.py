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
_EVENT_TYPES = frozenset({"snapshot", "ledger_append", "operation", "event_ledger", "heartbeat", "reset"})
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_MAX_EVENT_REPLAY = 4096
_SSE_REAUTHORIZATION_SECONDS = 15.0


class WebUiUnavailableError(RuntimeError):
    """Raised when the optional WebUI server dependencies are unavailable."""


class WebUiServiceError(RuntimeError):
    """A bridge error whose stable code may be returned to the browser."""

    def __init__(self, code: str, status_code: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class WebUiPrincipal:
    """Authenticated local administrator identity returned when a ticket is redeemed."""

    subject: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not self.subject:
            raise ValueError("webui principal subject must not be empty")


@dataclass(frozen=True, slots=True)
class WebUiEvent:
    """A redacted daemon event delivered to a browser over SSE."""

    event: str
    data: JsonObject
    identifier: str | None = None

    def __post_init__(self) -> None:
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
        if len(self.events) > _MAX_EVENT_REPLAY:
            raise ValueError("webui event replay exceeds the protocol limit")


class WebUiBridge(Protocol):
    """Daemon-owned data and authorization boundary used by the WebUI transport."""

    def issue_ticket(self) -> MaybeAwaitable[str]: ...

    def redeem_ticket(self, ticket: str) -> MaybeAwaitable[WebUiPrincipal | None]: ...

    def authorize_session(self, principal: WebUiPrincipal) -> MaybeAwaitable[bool]: ...

    def bootstrap(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]: ...

    def presentation(self, principal: WebUiPrincipal, locale: str | None) -> MaybeAwaitable[JsonObject]: ...

    def snapshot(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]: ...

    def operation_catalog(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]: ...

    def submit_operation(self, principal: WebUiPrincipal, request: JsonObject) -> MaybeAwaitable[JsonObject]: ...

    def operation(self, principal: WebUiPrincipal, operation_id: str) -> MaybeAwaitable[JsonObject | None]: ...

    def ledger(
        self, principal: WebUiPrincipal, cursor: str | None, limit: int
    ) -> MaybeAwaitable[JsonObject]: ...

    def audit(self, principal: WebUiPrincipal, cursor: str | None, limit: int) -> MaybeAwaitable[JsonObject]: ...

    def event_ledger(self, principal: WebUiPrincipal, cursor: str | None, limit: int) -> MaybeAwaitable[JsonObject]: ...

    def event_ledger_detail(self, principal: WebUiPrincipal, event_id: str) -> MaybeAwaitable[JsonObject | None]: ...

    def plugin_surfaces(self, principal: WebUiPrincipal) -> MaybeAwaitable[JsonObject]: ...

    def replay_events(
        self, principal: WebUiPrincipal, after_id: str | None, limit: int
    ) -> MaybeAwaitable[WebUiEventReplay]: ...

    def stream_events(self, principal: WebUiPrincipal, after_id: str | None) -> AsyncIterable[WebUiEvent]: ...


@dataclass(slots=True)
class _Session:
    principal: WebUiPrincipal
    csrf_token: str
    created_at: float
    last_seen_at: float


class _SessionStore:
    def __init__(self, *, idle_seconds: int, maximum_seconds: int) -> None:
        if idle_seconds < 60 or maximum_seconds < idle_seconds:
            raise ValueError("invalid WebUI session lifetime")
        self._idle_seconds = idle_seconds
        self._maximum_seconds = maximum_seconds
        self._sessions: dict[str, _Session] = {}

    def create(self, principal: WebUiPrincipal) -> tuple[str, _Session]:
        now = time.monotonic()
        session = _Session(principal, secrets.token_urlsafe(32), now, now)
        identifier = secrets.token_urlsafe(32)
        self._sessions[identifier] = session
        return identifier, session

    def get(self, identifier: str | None, *, touch: bool = True) -> _Session | None:
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
        if identifier is not None:
            self._sessions.pop(identifier, None)


async def _await[T](value: MaybeAwaitable[T]) -> T:
    if inspect.isawaitable(value):
        return await cast(Awaitable[T], value)
    return value


def _error(code: str, status_code: int) -> Any:
    return JSONResponse(status_code=status_code, content={"error": {"code": code}})


def _load_web_dependencies() -> None:
    if FastAPI is None:
        raise WebUiUnavailableError(
            "WebUI support is not installed; install `liteyukibot-v7[webui]` or `liteyukibot-v7-webui[server]`."
        )


def _asset_directory(path: Path | None) -> Path:
    if path is None:
        from . import static_assets

        directory = Path(str(static_assets()))
    else:
        directory = path
    if not directory.is_dir():
        raise WebUiUnavailableError("WebUI static assets are not installed.")
    return directory.resolve()


def _valid_host(host: str) -> bool:
    candidate = host.rsplit("@", 1)[-1].lower()
    if candidate.startswith("["):
        name = candidate.split("]", 1)[0] + "]"
    else:
        name = candidate.split(":", 1)[0]
    return name in {"127.0.0.1", "localhost", "[::1]"}


def _same_origin(request: Request, origin: str) -> bool:
    parsed = urlsplit(origin)
    if parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        return False
    return parsed.scheme == request.url.scheme and parsed.netloc.lower() == request.headers.get("host", "").lower()


def _sse(event: WebUiEvent) -> str:
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
    """Create an authenticated, loopback-only ASGI application around a daemon bridge."""
    _load_web_dependencies()
    assets = _asset_directory(asset_directory)
    sessions = _SessionStore(idle_seconds=session_idle_seconds, maximum_seconds=session_max_seconds)
    app = FastAPI(title="LiteyukiBot WebUI", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def loopback_policy(request: Request, call_next: Any) -> Any:
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
        try:
            return await _await(value)
        except WebUiServiceError:
            raise
        except Exception as error:
            raise WebUiServiceError("webui.bridge_unavailable", 503) from error

    @app.exception_handler(WebUiServiceError)
    async def service_error(_request: Request, error: WebUiServiceError) -> Any:
        return _error(error.code, error.status_code)

    @app.post("/api/v1/session")
    async def redeem_ticket(request: Request) -> Any:
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
        active = await authenticated(request)
        return {"csrf_token": active.csrf_token}

    @app.delete("/api/v1/session")
    async def close_session(request: Request) -> Any:
        await authenticated(request, csrf=True)
        sessions.remove(request.cookies.get(_COOKIE_NAME))
        response = Response(status_code=204)
        response.delete_cookie(_COOKIE_NAME, path="/")
        return response

    @app.get("/api/v1/bootstrap")
    async def bootstrap(request: Request) -> JsonObject:
        session = await authenticated(request)
        return await invoke(bridge.bootstrap(session.principal))

    @app.get("/api/v1/presentation")
    async def presentation(request: Request, locale: str | None = None) -> JsonObject:
        session = await authenticated(request)
        value = dict(await invoke(bridge.presentation(session.principal, locale)))
        from . import __version__

        value["webui_version"] = __version__
        return value

    @app.get("/api/v1/snapshot")
    async def snapshot(request: Request) -> JsonObject:
        session = await authenticated(request)
        return await invoke(bridge.snapshot(session.principal))

    @app.get("/api/v1/operations/catalog")
    async def operation_catalog(request: Request) -> JsonObject:
        session = await authenticated(request)
        return await invoke(bridge.operation_catalog(session.principal))

    @app.post("/api/v1/operations")
    async def submit_operation(request: Request) -> JsonObject:
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
        session = await authenticated(request)
        record = await invoke(bridge.operation(session.principal, operation_id))
        if record is None:
            raise WebUiServiceError("webui.operation_not_found", 404)
        return record

    @app.get("/api/v1/ledger")
    async def ledger(request: Request, cursor: str | None = None, limit: int = 100) -> JsonObject:
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        return await invoke(bridge.ledger(session.principal, cursor, limit))

    @app.get("/api/v1/audit")
    async def audit(request: Request, cursor: str | None = None, limit: int = 100) -> JsonObject:
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        return await invoke(bridge.audit(session.principal, cursor, limit))

    @app.get("/api/v1/event-ledger")
    async def event_ledger(request: Request, cursor: str | None = None, limit: int = 100) -> JsonObject:
        session = await authenticated(request)
        if not 1 <= limit <= 500:
            raise WebUiServiceError("webui.invalid_page_size", 400)
        page = await invoke(bridge.event_ledger(session.principal, cursor, limit))
        if page.get("error") == "invalid_cursor":
            raise WebUiServiceError("webui.invalid_event_ledger_cursor", 400)
        return page

    @app.get("/api/v1/event-ledger/{event_id}")
    async def event_ledger_detail(request: Request, event_id: str) -> JsonObject:
        session = await authenticated(request)
        record = await invoke(bridge.event_ledger_detail(session.principal, event_id))
        if record is None:
            raise WebUiServiceError("webui.event_ledger_not_found", 404)
        return record

    @app.get("/api/v1/plugins/surfaces")
    async def plugin_surfaces(request: Request) -> JsonObject:
        session = await authenticated(request)
        return await invoke(bridge.plugin_surfaces(session.principal))

    @app.get("/api/v1/events")
    async def events(request: Request) -> Any:
        session = await authenticated(request)
        after_id = request.headers.get("last-event-id")
        replay = await invoke(bridge.replay_events(session.principal, after_id, _MAX_EVENT_REPLAY))

        async def stream() -> AsyncIterable[str]:
            next_reauthorization_at = time.monotonic() + _SSE_REAUTHORIZATION_SECONDS

            async def reauthorize_if_due() -> None:
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
        """Start the service and return a fragment handoff URL for a fresh daemon ticket."""
        if self._server is None:
            await self.start()
        ticket = await _await(self._bridge.issue_ticket())
        if not ticket:
            raise WebUiServiceError("webui.ticket_unavailable", 503)
        return self.handoff_url(ticket)

    def handoff_url(self, ticket: str) -> str:
        """Build a browser-only ticket handoff URL without placing it in an HTTP request."""
        if not ticket:
            raise ValueError("WebUI ticket must not be empty")
        return f"http://{self._url_host()}:{self.port}/#ticket={quote(ticket, safe='')}"

    def status(self) -> JsonObject:
        """Return a redacted, JSON-safe server lifecycle snapshot for daemon control."""
        state = "running" if self._server is not None and self._server.started else "stopped"
        return {"state": state, "host": self.host, "port": self.port}

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            await self._task
        self._server = None
        self._task = None

    def _url_host(self) -> str:
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
