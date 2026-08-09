# ADR 0010: Publish Developer Conformance Harnesses

- Status: Accepted
- Date: 2026-08-09

## Context

The native plugin API and runtime protocols are documented, but third-party authors
currently have to reconstruct internal application wiring to test them. Example
code that only demonstrates model construction does not prove plugin discovery,
lifecycle cleanup, authenticated runtime negotiation, or correlation behavior.

The developer surface must remain smaller than the kernel. Adding a test
framework, a second plugin host, or an in-memory protocol imitation would create
new behavior instead of verifying the accepted contracts.

## Decision

`liteyukibot.testing` provides two dependency-free, single-use async context
managers. It never imports pytest and is included in the normal distribution.

`PluginTestHarness` runs one `PluginDefinition` through the real
`PluginManager`, `EventBus`, `ServiceRegistry`, Action path, and managed-task
lifecycle. It accepts a test root, plugin config, declared dependency values,
and an optional Action executor. It exposes the loaded context, immutable
recorded Actions, event publication, and service lookup. The default Action
result is a correlated success. Multi-plugin dependency topology remains a
kernel integration test and does not receive a second abstraction.

The harness does not infer EventBus ownership. Plugins must retain and remove
their subscriptions in their stop callback. The manager continues to own
managed-task cancellation and removal of services provided by the plugin.

`RuntimeTestHarness` runs one explicit `RuntimeSpec.command` through a real
`RuntimeSupervisor` and loopback subprocess connection. It records
child-originated Events and Actions, supplies correlated default success
results, and exposes core-to-child Event and Action calls. Runtime state,
negotiated protocol version, and capabilities are observable without exposing
the mutable supervisor record.

Every child runtime has exactly one physical receive pump. Work that may await
`RuntimeClient.execute_action()` runs in separately tracked tasks so the receive
pump can route its `ActionResponse`. Children acknowledge every Event, respond
to every Action request, cancel and collect their work on Shutdown, and never
implement their own reconnect loop. Restart policy belongs to the supervisor.

Supervisor Event and Action dispatch reject non-positive timeouts before
runtime lookup or transmission. Duplicate in-flight correlation IDs are
rejected before pending state is changed. `RuntimeSpec` rejects empty command
sequences and empty command arguments.

The installable examples under `examples/native-plugin` and
`examples/custom-runtime` use only public imports. Native entry-point metadata
must resolve to a `PluginDefinition` whose manifest ID equals the entry-point
name.

## Consequences

Authors can verify real lifecycle and wire behavior without depending on
LiteyukiBot's internal test suite or adding a test dependency to production.
The helpers intentionally favor conformance over isolated mocking, so custom
runtime tests launch a real subprocess and native plugin tests exercise the real
bounded EventBus.

This decision does not add pytest fixtures, scaffolding commands, automatic
dependency installation, multi-plugin simulation, a runtime handler framework,
background protocol readers, automatic reconnect, hot reload, sandboxing,
remote transport, or PyO3.
