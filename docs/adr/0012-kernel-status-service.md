# ADR 0012: Expose Kernel Status as a Versioned Service

- Status: Accepted
- Date: 2026-08-10

## Context

The application already reports process state through its authenticated local
control channel and optional loopback HTTP API. Native plugins need the same
operational facts for first-party commands, but reaching into `LiteyukiApp`,
the plugin manager, or the runtime supervisor would couple them to mutable
kernel internals.

System resource metrics are platform-specific and are not part of the current
dependency budget. Runtime wire peers also do not need this process-local
observability contract.

## Decision

The kernel provides `liteyukibot.kernel.status@1` in the service registry during
application construction, before plugin discovery and dependency resolution.
The registered value implements `KernelStatusProvider.snapshot()` and does not
expose the owning `LiteyukiApp`.

`KernelStatusSnapshot` is a frozen in-process value containing the distribution
version, application state, monotonic uptime, sorted plugin and runtime states,
and the outstanding EventBus count. Plugin and runtime mappings are immutable.
The uptime is zero before startup, advances while the application is running,
and freezes after shutdown or startup failure.

`LiteyukiApp.status()` remains the JSON-facing compatibility surface for the
control and HTTP servers. It serializes a fresh snapshot into ordinary
dictionaries, so no immutable internal mapping is handed to a transport.

The service does not expose restart controls, mutable manager objects, CPU or
memory metrics, adapter objects, or configuration secrets. It does not change
Event/Action schemas or the runtime IPC protocol.

## Consequences

Native plugins can declare and resolve an explicit, versioned dependency on
kernel observability without gaining a general application handle. Status
rendering remains outside the kernel, allowing first-party or third-party
plugins to choose their own presentation and access policy.

The snapshot is deliberately small. Adding platform resource metrics or new
operational controls requires a separate contract and evidence that it belongs
in the kernel dependency budget.
