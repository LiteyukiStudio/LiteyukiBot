# v7 Alpha 3: First-Party Business Plugin Migration

> **Planned implementation contract.** This document records the agreed Alpha 3
> boundary. It does not claim that any business plugin has been migrated or
> released.

Alpha 3 migrates the first-party business chain onto Alpha 2's extension,
permission, and broker Tool contracts. It starts only after Alpha 2 is merged.

## Release boundary

The lockstep set advances to `7.0.0a3` under tag `v7.0.0a3`. The signed GitHub
Release additionally contains these independent first-party assets:

| Distribution | Version |
| --- | --- |
| `liteyukibot-v7-permissions` | `0.3.0a2` |
| `liteyukibot-v7-commands` | `0.3.0a1` |
| `liteyukibot-v7-resources` | `0.2.0a1` |
| `liteyukibot-v7-profile` | `0.2.0a1` |
| `liteyukibot-v7-essentials` | `0.3.0a1` |
| `liteyukibot-v7-agent-resolver` | `0.2.0a1` |
| `liteyukibot-v7-functions` | `0.1.0a3` |

Every asset requires `liteyukibot-v7==7.0.0a3`; dependencies inside the
migrated chain use the exact Alpha 3 versions. Functions is a compatibility
rebuild only and retains its v6 executor behavior. All assets remain GitHub
Release-only and inherit Alpha 1's Sigstore and no-PyPI rules.

## Dual-host business chain

Permissions, Commands, Resources, Profile, and Essentials use explicit
`ExtensionManifest(api_version=2)` declarations and each publish Native and
Cordis entry points. Their service core must be host-neutral; Native and
Cordis adapters own event/subscription lifecycle only.

Commands, Resources, and Profile upgrade their `ServiceKey` major to `2`.
The dependency chain is Permissions -> Commands -> Resources -> Profile, with
Essentials consuming Commands and optionally Profile. Agent Resolver becomes a
pure ToolDeclaration/ToolCatalog resolution library with no Agent runtime,
provider, sandbox, or plugin lifecycle.

Native adapters are limited. Cordis adapters are full by default and must also
be tested after `[cordis.access]` lowers them to limited. No package may import
another host implementation or a platform adapter SDK.

## Intentional business hard cut

Alpha 3 provides no compatibility translation for business configuration,
command configuration, or Profile SQLite data. A v1 configuration shape or
database schema must fail plugin startup with the stable
`migration_required` diagnostic. Implementations must not delete, recreate,
partially read, or silently migrate legacy state.

## Business Tool gate

Resources and Profile first implement their structured inspect, set, and
delete Tools. They must pass the complete Tool RPC path, including host schema
validation, caller/provider authorization, broker lease binding, replay,
disconnect, and redacted diagnostics.

Only after that gate passes, Alpha 3 adds all remaining direct business Tools
in the same release:

- Permissions checks the current invocation context only.
- Commands invokes an already registered command through its existing command
  authorization path.
- Essentials provides help and status.

No business Tool may run arbitrary Python, shell commands, generic actions, or
caller-supplied principal overrides. Failure of the Resources/Profile gate
splits the work into `a3+1`; Alpha 3 is not released as a partial Tool rollout.

## Completion gate

Every independent asset must build, install, enable, disable, and remove in
isolation. Tests cover Native/Cordis behavior, Cordis downscoping, service-major
mismatch, cross-package startup ordering, hard-cut configuration/database
rejection, Tool schemas, Tool authorization, and retained broker outcomes.

The complete repository quality gate, workspace build, every affected isolated
verifier, and signed Alpha bundle verification must pass. Agent implementation,
RAG, sandbox workers, Function DSL, generic adapter migration, and legacy
runtime migration remain outside Alpha 3.

## Alpha 4 handoff

Alpha 4 starts from the frozen broker Tool catalog and the business-package
v2 services. It implements the [generic adapter, OneBot, and Satori broker
bridge boundary](v7-alpha-4-adapter-bridge.md) without importing platform SDKs
into the root kernel.
