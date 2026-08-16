# Local WebUI Service v1

- Specification version: `1`
- Applies to: `liteyukibot-v7[webui]` and `liteyukibot-v7-webui[server]`
- Compatibility: pre-stable

## Boundary

The WebUI is a local observation and controlled-management surface.  It is
served only by the instance daemon on loopback; the browser never connects to
a runtime worker, plugin process, operation database, or management command
parser directly.

`liteyuki web open` asks the running daemon to issue a one-time handoff URL.
The URL contains a short-lived ticket in its fragment, so it is not sent in an
HTTP request.  The SPA redeems it once, receives an HttpOnly, `SameSite=Strict`
session cookie and uses a session-bound CSRF token for later mutations.

The service rejects non-loopback Host headers and cross-origin unsafe requests.
It is not a LAN listener, reverse-proxy endpoint, remote control plane, or
plugin-hosted HTTP extension point.

## API And Streaming

The authenticated `/api/v1` namespace exposes bootstrap state, kernel
snapshots, operation catalog and status, audit records, plugin surfaces, the
read-only event ledger, and an SSE event stream. Responses are JSON-safe
snapshots. The stream supports
`Last-Event-ID`; when an event has expired from the bounded replay buffer, the
service emits a `reset` event rather than silently continuing from an
incomplete history.

`GET /api/v1/event-ledger?cursor=&limit=` returns a bounded page with a limit
of `1..500`; `GET /api/v1/event-ledger/{event_id}` returns one retained detail
or `404`. Both endpoints are observation-only. SSE emits an `event_ledger`
summary only, so consumers fetch detail explicitly instead of receiving a
payload-bearing delivery stream.

The daemon validates the worker projection and HMAC-redacts source runtime ID,
source event ID, bot ID, and conversation ID using its diagnostic audit key.
It omits event payloads, message segments, action payloads, credentials, and
raw exceptions from every response and SSE event.

The UI is a static SPA served by the same local service.  `assets.manifest.json`
contains the SHA-256 and byte size of every staged asset.  Release workflows
must build `webui/`, run `scripts/stage_webui_assets.py`, then run the installed
package verifier before publishing the `webui` distribution.

## Operation Ownership

The daemon owns the operation ledger, including authorization, idempotency,
state transition, durable audit records, redaction, and the queue visible to
both WebUI and CLI.  A worker exposes only a structured operation catalog and
executes a request already accepted by that ledger.  It must not create a
second ledger for a daemon-managed instance.

WebUI mutation requests contain an operation ID, validated JSON input, target,
idempotency key, and confirmation evidence.  Raw management-command strings
are not a browser API.  Every catalogued mutation requires an explicit
confirmation; runtime stop and plugin rollback additionally require the typed
target to match.  The current WebUI catalog contains runtime start, stop, and
restart plus plugin install, update, enable, disable, and rollback.  Plugin
uninstall and garbage collection remain terminal-only in this version.

## Evidence

```bash
uv run --extra webui pytest packages/webui/tests tests/test_daemon.py tests/test_management.py tests/test_operations.py
pnpm --dir webui typecheck
pnpm --dir webui build
pnpm --dir webui test:e2e
uv run python scripts/stage_webui_assets.py
uv run python scripts/check_release.py --package webui
```
