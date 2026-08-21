# v7 Alpha 8b: DevCLI and Atomic Instance Updates

> **Implemented Alpha 8b contract.** The source tree and local validation now
> cover this contract. Official publication still requires the real Sigstore
> signature and the CI release gates described below.

Alpha 8b is the second half of the ecosystem milestone. Alpha 8a first
validates third-party Native/Cordis calls into a versioned runtime bridge API;
this document retains the separate Python development scaffold and the first
verified whole-instance update transaction.

The combined Alpha 8 release is gated on both Alpha 8a and Alpha 8b.

## DevCLI

`liteyukibot-v7-devcli` provides `liteyuki-dev`; the existing `liteyuki`
command remains the kernel CLI. `@liteyuki/dev` is only a thin npm launcher for
the installed Python command and does not implement verification or updates.

`verify`, `stage`, `update`, `status`, and `rollback` accept an official GitHub
Release bundle or a local downloaded copy. They verify tag-bound Sigstore
identity, canonical manifest, hashes, wheel metadata, and the signed resolved
dependency lock before staging an immutable profile.

## Update transaction

Only instances whose broker, bridges, and kernel are registered with the daemon
are eligible. The updater freezes broker admission, drains active deliveries
within a bound, freezes kernel business activity, stops kernel/bridges/broker,
atomically switches profile, verifies staged executables, then starts broker,
bridges, and kernel in order.

Any failed start or health check stops the candidate set, restores the previous
verified profile, restarts the prior set, and retains ledger evidence. Manual
rollback remains available. The broker itself remains non-supervisory; this
process orchestration belongs only to the daemon update transaction.

## Editor and WebUI

The release contains a TextMate grammar and VS Code integration for LYF. WebUI
uses the same grammar for read-only resource highlighting and parser
diagnostics. Browser editing and execution remain outside Alpha 8.

## Completion

The Alpha 8b implementation is present at `v7.0.0a8`: every independent
first-party package is rebuilt against that exact kernel, the DevCLI stages
offline verified profiles, the daemon owns the atomic Broker/Bridge/Kernel
transaction, and LYF grammar/diagnostics are shared by VS Code and WebUI.
Tests cover invalid bundles, Sigstore/hash/lock mismatch, staging interruption,
managed-process eligibility, drain timeout, startup ordering, health failure,
automatic/manual rollback, recovery after interruption, TextMate fixtures, VS
Code checks, WebUI rendering, and full repository release gates. The release
workflow must still produce the official signed bundle before publication.
