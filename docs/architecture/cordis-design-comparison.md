# Cordis Design Comparison

## Scope

This document distinguishes Koishi/Cordis, DeepSeek Harness, and LiteyukiBot
v7. Shared terms do not imply source, ABI, or plugin compatibility.

| System | Cordis role | Liteyuki position |
| --- | --- | --- |
| Koishi | JavaScript bot application and plugin framework | Reached through a Classic runtime bridge, not reused by Cordis Plugin v1 |
| DeepSeek Harness | Dynamic product composition runtime | Source of lifecycle and composition lessons |
| LiteyukiBot | Python in-process composition framework plus independent bridge broker | New Liteyuki ecosystem, not a Rust processor or JS compatibility layer |

## What Liteyuki Adopts

Liteyuki adopts scoped dependencies, ownership of registrations and tasks,
deterministic disposal, dependency-aware activation, and explicit composition
modes. Cordis Plugin v1 exposes these to Python plugin authors alongside the
existing Native Plugin v1 surface.

The first-party presets are ordered listener, parallel fanout, waterfall
middleware, and directed route. Custom schedulers may be installed with a
host-managed best-effort wrapper. A plugin can choose its local composition
model; the host records only lifecycle outcomes it can reliably observe.

## What Remains Different

Liteyuki does not promise Koishi plugin compatibility, JavaScript Session/Bot
objects, or a shared framework-object graph. Framework-native behavior belongs
to the bridge that owns its SDK. A NoneBot or separately maintained optional
bridge is installed through that framework's native plugin API and converts at
the Liteyuki bridge boundary.

The standalone broker owns cross-process registration, event IDs, directed
subscriptions, ledger state, and portable action return. Runtime hosts own
their own processes. This avoids making either a Classic runtime or Cordis the
parent of the other.

## Tradeoff

The product deliberately makes different choices by boundary:

- the kernel/broker and Classic bridges optimize stable contracts and
  performance;
- Python Cordis plugins optimize authoring velocity and in-process performance;
- limited access is only promised at an isolated bridge/runtime boundary;
- first-party stable paths are release gates, while third-party plugins are
  allowed broader behavior without inheriting that guarantee.

This is not a claim that one framework simultaneously maximizes stability,
ecosystem, and performance. It is a split of those tradeoffs across explicit
deployment and trust boundaries.

## Beta6 Contract Pointer

The Beta6 implementation target is Python-first and independent of the kernel:
`liteyukibot-v7-cordis` is discovered through host and plugin entry points, and
does not reuse the rejected Rust/PyO3 `runtime-cordis` package. Its four
official presets, scope lifecycle, event identity rule, and audit-only policy
are maintained in [Cordis Plugin v1](cordis-plugin-v1.md).
