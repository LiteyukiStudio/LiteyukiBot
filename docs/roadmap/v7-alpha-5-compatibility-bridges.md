# v7 Alpha 5: v6 and MoFox Compatibility Bridges

> **Implementation contract.** The Alpha 5 bridge migration is implemented on
> `feat/alpha5-compatibility-bridges`. The release boundary remains planned:
> package versions and the signed Alpha bundle are intentionally unchanged.

Alpha 5 removes the remaining legacy child-runtime boundary while retaining the
narrow v6 migration surface and an experimental MoFox integration.

## Release boundary

The lockstep set advances to `7.0.0a5`. Every independent first-party package
is rebuilt for this Alpha and exactly depends on `liteyukibot-v7==7.0.0a5`.
The signed bundle adds rebuilt v6 and MoFox bridge assets; no Alpha artifact is
published to PyPI.

## v6 bridge

`runtime-v6` becomes an experimental limited `liteyukibot.bridges` bridge. It
loads only configured `liteyukibot.v6_plugins` entry points and rejects legacy
module paths, plugin directories, object transport, CallApi, EditMessage, and
historical runtime configuration with `migration_required`.

The retained surface is process-local matcher ordering/blocking, Session,
MessageEvent, lifecycle callbacks, and ordered `event.reply()` conversion to
the source bridge's `message.send`. Restart requests perform bounded cleanup
and exit for an external process manager; the broker never supervises it.

## MoFox bridge

`runtime-mofox` becomes an experimental limited bridge. It uses only a
configured isolated Neo-MoFox workspace and its fixed upstream verifier
prerequisite. Liteyuki managed projection, copy, and symlink loading are
removed. Headless output can only become ordered `message.send` requests to the
source bridge.

## Topic and completion boundary

Limited compatibility bridges use broker dot-segment topic patterns. `*` matches
one complete segment only; there is no regex or recursive wildcard. Examples
include `onebot.*.message.*` and `satori.message.*`.

Tests cover pattern matching, v6 matcher/session behavior, entry-point loading,
legacy rejection, reply ordering, restart cleanup, MoFox workspace isolation,
upstream verification, source-action failure, disconnect, and release installs.

## Alpha 6 handoff

Alpha 6 replaces the old Agent runtime/plugin boundary with separate Agent and
sandbox broker bridges, reusing the frozen Tool RPC catalog.
