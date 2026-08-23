# Trusted capability boundaries

This document explains capabilities that are intentionally retained even
though malformed input, excessive content, or compromised trusted code could
make them dangerous. The code-level docstrings link here instead of duplicating
the complete architecture rationale.

## LYIP frames

LYIP transports opaque peer payloads over local ZMQ sockets. The capability is
required because framework bridges run outside the protocol-neutral kernel.
Peers are authenticated at broker registration; generation, lane, type,
sequence, stream, and lease identities are validated. Payloads are capped at
8 MiB and encoded frames at 12 MiB. These checks bound memory and confusion
risks but do not turn an authenticated bridge into hostile-code containment.

## Broker retention

The Broker retains terminal records for diagnostics and idempotent result
handling. Retention is necessary to explain delivery failures and reject
conflicting replays. Active records are count-bounded and receive content only
through bounded LYIP frames. Terminal records are independently bounded by
count, retained wire-content bytes, and TTL; all active delivery and lane
indices are removed on settlement.

## Plugin artifacts and native code

Plugin installation downloads immutable, digest-addressed archives from
credential-free HTTPS sources. Downloads, ZIP member count, individual member
size, total extracted size, paths, and symbolic links are checked before a
generation is activated. Alpha12 also bounds index size, dependency closure,
generation inputs, cumulative downloaded bytes, and retained active/previous
generation state. The stable NoneBot bridge probes a candidate load plan before
activation and the daemon restores the previous graph when candidate startup
fails. Native plugins still execute as trusted Python code inside the kernel;
managed generations are lifecycle and reproducibility boundaries, not hostile
code sandboxes. The capability is retained for first-party and explicitly
trusted extensions; untrusted code belongs in an external runtime or sandbox.

## Local control and diagnostics

Control and diagnostics endpoints bind to loopback and use random or
vault-backed tokens compared without timing-sensitive equality. Request sizes,
timeouts, operation catalogs, and redacted projections constrain exposure.
They remain available because the daemon, CLI, and WebUI need a local
management plane. Loopback is not treated as authentication by itself.

## Secret vault

The local vault encrypts configured secrets with AES-GCM under a key derived
from the operator passphrase with scrypt. Authenticated encryption, restrictive
file permissions, and atomic replacement protect secrets at rest and detect
tampering. A process running as the same operating-system user can still read
plaintext after unlock; the vault is retained to protect stored configuration,
not to claim same-user process isolation.

## Agent worker execution

Agent workers can execute configured callables and selected file, process, or
network helpers. Fresh worker processes, capability policy, path checks,
timeouts, and output/file byte limits reduce persistence and resource abuse.
This is a policy boundary for trusted deployments, not a complete operating
system sandbox; arbitrary third-party worker code must run under an external
isolation boundary.
