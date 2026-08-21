from __future__ import annotations

from collections.abc import AsyncIterable, Mapping
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from liteyukibot_webui import WebUiEvent, WebUiEventReplay, WebUiPrincipal, WebUiServer, create_app
from liteyukibot_webui import service as webui_service
from liteyukibot_webui.service import JsonObject


class Bridge:
    def __init__(self) -> None:
        self.principal = WebUiPrincipal("local-admin", frozenset({"runtime.control"}))
        self.submissions: list[JsonObject] = []
        self.event_delivery_queries: list[tuple[dict[str, str], str | None, int]] = []

    async def issue_ticket(self) -> str:
        return "unused"

    async def redeem_ticket(self, ticket: str) -> WebUiPrincipal | None:
        return self.principal if ticket == "ticket" else None

    async def authorize_session(self, principal: WebUiPrincipal) -> bool:
        return principal == self.principal

    async def bootstrap(self, principal: WebUiPrincipal) -> JsonObject:
        return {"subject": principal.subject}

    async def presentation(self, _principal: WebUiPrincipal, locale: str | None) -> JsonObject:
        return {"locale": locale or "en-US", "messages": {"webui.nav.overview": "Overview"}}

    async def snapshot(self, _principal: WebUiPrincipal) -> JsonObject:
        return {"state": "ready"}

    async def operation_catalog(self, _principal: WebUiPrincipal) -> JsonObject:
        return {"operations": ["runtime.restart"]}

    async def submit_operation(self, _principal: WebUiPrincipal, request: JsonObject) -> JsonObject:
        self.submissions.append(request)
        return {"id": "operation-1", "state": "queued"}

    async def operation(self, _principal: WebUiPrincipal, operation_id: str) -> JsonObject | None:
        return {"id": operation_id} if operation_id == "operation-1" else None

    async def ledger(self, _principal: WebUiPrincipal, cursor: str | None, limit: int) -> JsonObject:
        return {"cursor": cursor, "limit": limit, "entries": []}

    async def audit(self, _principal: WebUiPrincipal, cursor: str | None, limit: int) -> JsonObject:
        return {"cursor": cursor, "limit": limit, "entries": []}

    async def plugin_surfaces(self, _principal: WebUiPrincipal) -> JsonObject:
        return {"generation": 1, "surfaces": []}

    async def lyf_resources(self, _principal: WebUiPrincipal) -> JsonObject:
        return {"read_only": True, "grammar": "source.lyf", "items": []}

    async def event_deliveries(
        self, _principal: WebUiPrincipal, filters: Mapping[str, str], cursor: str | None, limit: int
    ) -> JsonObject:
        self.event_delivery_queries.append((dict(filters), cursor, limit))
        return {
            "broker": {
                "state": "ready",
                "active": 1,
                "active_capacity": 32,
                "terminal": 2,
                "terminal_capacity": 128,
                "bridges": [],
            },
            "items": [{"id": "event-1", "topic": "message.created", "source": "source:abc", "status": "delivered"}],
            "next_cursor": None,
        }

    async def event_delivery(self, _principal: WebUiPrincipal, event_id: str) -> JsonObject | None:
        if event_id != "event-1":
            return None
        return {
            "id": event_id,
            "topic": "message.created",
            "source": "source:abc",
            "status": "delivered",
            "deliveries": [],
            "timeline": [],
        }

    async def replay_events(
        self, _principal: WebUiPrincipal, after_id: str | None, limit: int
    ) -> WebUiEventReplay:
        assert limit == 4096
        if after_id == "expired":
            return WebUiEventReplay((), reset=True)
        return WebUiEventReplay((WebUiEvent("snapshot", {"state": "ready"}, "2"),))

    async def stream_events(self, _principal: WebUiPrincipal, _after_id: str | None) -> AsyncIterable[WebUiEvent]:
        if False:
            yield WebUiEvent("heartbeat", {})


def _client(
    tmp_path: Path,
    bridge: Bridge | None = None,
    *,
    session_idle_seconds: int = 1800,
    session_max_seconds: int = 28800,
) -> tuple[TestClient, Bridge]:
    (tmp_path / "index.html").write_text("<main>Liteyuki</main>", encoding="utf-8")
    resolved_bridge = bridge or Bridge()
    return (
        TestClient(
            create_app(
                resolved_bridge,
                asset_directory=tmp_path,
                session_idle_seconds=session_idle_seconds,
                session_max_seconds=session_max_seconds,
            ),
            base_url="http://127.0.0.1:9321",
        ),
        resolved_bridge,
    )


def _session(client: TestClient) -> str:
    response = client.post("/api/v1/session", json={"ticket": "ticket"}, headers={"Origin": "http://127.0.0.1:9321"})
    assert response.status_code == 200
    return str(response.json()["csrf_token"])


def test_ticket_session_and_mutation_csrf_policy(tmp_path: Path) -> None:
    client, bridge = _client(tmp_path)
    assert client.get("/api/v1/bootstrap").json() == {"error": {"code": "webui.session_required"}}
    csrf_token = _session(client)

    forbidden = client.post(
        "/api/v1/operations",
        json={"operation": "runtime.restart"},
        headers={"Origin": "http://127.0.0.1:9321"},
    )
    assert forbidden.json() == {"error": {"code": "webui.csrf_required"}}

    submitted = client.post(
        "/api/v1/operations",
        json={"operation": "runtime.restart"},
        headers={"Origin": "http://127.0.0.1:9321", "X-CSRF-Token": csrf_token},
    )
    assert submitted.json() == {"id": "operation-1", "state": "queued"}
    assert bridge.submissions == [{"operation": "runtime.restart"}]


def test_presentation_is_session_scoped_and_carries_the_package_version(tmp_path: Path) -> None:
    client, _bridge = _client(tmp_path)
    _session(client)
    response = client.get("/api/v1/presentation?locale=zh-CN")
    assert response.status_code == 200
    assert response.json()["locale"] == "zh-CN"
    assert response.json()["messages"] == {"webui.nav.overview": "Overview"}
    assert isinstance(response.json()["webui_version"], str)


def test_loopback_origin_and_host_are_enforced(tmp_path: Path) -> None:
    client, _bridge = _client(tmp_path)
    assert client.get("/", headers={"Host": "example.test"}).json() == {"error": {"code": "webui.invalid_host"}}
    assert client.post("/api/v1/session", json={"ticket": "ticket"}).json() == {
        "error": {"code": "webui.origin_required"}
    }
    assert client.post(
        "/api/v1/session", json={"ticket": "ticket"}, headers={"Origin": "http://example.test"}
    ).json() == {"error": {"code": "webui.invalid_origin"}}


def test_event_deliveries_are_authenticated_and_filter_inputs_are_bounded(tmp_path: Path) -> None:
    client, bridge = _client(tmp_path)
    assert client.get("/api/v1/event-deliveries").json() == {"error": {"code": "webui.session_required"}}
    _session(client)

    response = client.get(
        "/api/v1/event-deliveries",
        params={
            "state": "delivered",
            "topic": "message.created",
            "source": "source:abc",
            "limit": 20,
            "cursor": "next",
        },
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["source"] == "source:abc"
    assert bridge.event_delivery_queries == [
        ({"state": "delivered", "topic": "message.created", "source": "source:abc"}, "next", 20)
    ]
    assert client.get("/api/v1/event-deliveries", params={"failure": ""}).json() == {
        "error": {"code": "webui.invalid_event_delivery_filter"}
    }
    assert client.get("/api/v1/event-deliveries", params={"limit": 501}).json() == {
        "error": {"code": "webui.invalid_page_size"}
    }


def test_event_delivery_detail_hides_missing_records_behind_a_stable_code(tmp_path: Path) -> None:
    client, _bridge = _client(tmp_path)
    _session(client)

    detail = client.get("/api/v1/event-deliveries/event-1")
    assert detail.status_code == 200
    assert detail.json()["id"] == "event-1"
    assert client.get("/api/v1/event-deliveries/missing").json() == {
        "error": {"code": "webui.event_delivery_not_found"}
    }
    assert client.get(f"/api/v1/event-deliveries/{'x' * 257}").json() == {
        "error": {"code": "webui.invalid_event_delivery_id"}
    }


def test_sse_replay_and_reset_are_protocol_events(tmp_path: Path) -> None:
    client, _bridge = _client(tmp_path)
    _session(client)
    replay = client.get("/api/v1/events")
    assert replay.headers["content-type"].startswith("text/event-stream")
    assert "id: 2\nevent: snapshot\ndata: {\"state\":\"ready\"}" in replay.text

    reset = client.get("/api/v1/events", headers={"Last-Event-ID": "expired"})
    assert "event: reset\ndata: {\"reason\":\"replay_unavailable\"}" in reset.text


def test_sse_reauthorizes_before_emitting_follow_up_events(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class RevokedBridge(Bridge):
        def __init__(self) -> None:
            super().__init__()
            self.authorized = True

        async def authorize_session(self, principal: WebUiPrincipal) -> bool:
            return self.authorized and await super().authorize_session(principal)

        async def stream_events(self, _principal: WebUiPrincipal, _after_id: str | None) -> AsyncIterable[WebUiEvent]:
            self.authorized = False
            yield WebUiEvent("operation", {"id": "must-not-be-delivered"})

    monkeypatch.setattr(webui_service, "_SSE_REAUTHORIZATION_SECONDS", 0.0)
    client, _bridge = _client(tmp_path, RevokedBridge())
    _session(client)

    response = client.get("/api/v1/events")

    assert "event: reset\ndata: {\"reason\":\"webui.session_invalid\"}" in response.text
    assert "must-not-be-delivered" not in response.text


def test_sse_idle_expiry_does_not_continue_stream_delivery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    class ExpiringBridge(Bridge):
        async def stream_events(self, _principal: WebUiPrincipal, _after_id: str | None) -> AsyncIterable[WebUiEvent]:
            clock[0] = 61.0
            yield WebUiEvent("operation", {"id": "must-not-be-delivered"})

    clock = [0.0]
    monkeypatch.setattr("liteyukibot_webui.service.time.monotonic", lambda: clock[0])
    monkeypatch.setattr(webui_service, "_SSE_REAUTHORIZATION_SECONDS", 0.0)
    client, _bridge = _client(
        tmp_path,
        ExpiringBridge(),
        session_idle_seconds=60,
        session_max_seconds=300,
    )
    _session(client)

    response = client.get("/api/v1/events")

    assert "event: reset\ndata: {\"reason\":\"webui.session_required\"}" in response.text
    assert "must-not-be-delivered" not in response.text


def test_static_spa_fallback_is_packaged_by_the_server(tmp_path: Path) -> None:
    client, _bridge = _client(tmp_path)
    response = client.get("/runtimes")
    assert response.status_code == 200
    assert response.text == "<main>Liteyuki</main>"


async def test_server_open_issues_fragment_handoff_and_reports_bound_port(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<main>Liteyuki</main>", encoding="utf-8")
    server = WebUiServer(Bridge(), asset_directory=tmp_path)
    try:
        handoff = await server.open()
        status = server.status()
        assert status["state"] == "running"
        assert isinstance(status["port"], int) and status["port"] > 0
        assert handoff == f"http://127.0.0.1:{status['port']}/#ticket=unused"
    finally:
        await server.stop()
