# ADR 0024: Instance Daemon Lifecycle

- Status: Accepted
- Date: 2026-08-13

## Context

One kernel process cannot safely reload all native plugins, child runtimes, and
their event work in place. Operators also need several isolated bots from one
workspace without sharing locks or state.

## Decision

Each `liteyuki run` owns a local daemon for one named instance. The daemon
holds `.liteyuki/instances/<name>/daemon.lock` and publishes an authenticated
loopback `daemon.json`; it starts exactly one worker process. The worker alone
continues to hold `<data_dir>/instance.lock` and publishes its existing runtime
control descriptor. Named instances derive data, cache, and logs below their
instance root; the default preserves configured paths.

The daemon can stop or explicitly restart its worker and may retry abnormal
worker exits under bounded configuration. It never persists decrypted runtime
secrets: they are supplied only in inherited process memory. Native plugins
may consume `liteyukibot.instance_daemon@1` for JSON-safe status and a
rate-limited restart request.

## Consequences

Daemon control is local and authenticated, not an HTTP administration API.
Whole-worker restart becomes a defined lifecycle boundary without changing
runtime IPC. File watching and development-only controls remain a separate
opt-in layer.
