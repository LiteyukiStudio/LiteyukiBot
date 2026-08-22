# v7 Alpha 10.2: Ecosystem and Release Proof

Alpha10.2 proves the Alpha10.1 portable facade and B7 bridge boundary from
installable artifacts. It improves contributor and release evidence without
adding a provider, a portable operation, or an Alpha11 qualification gate.

## Work

- Generate the four stable Runtime API v1.2 operations from the kernel-owned
  catalog helper and record a deterministic SHA-256 catalog fingerprint in
  non-empty `BridgeManifest` values.
- Extend the NoneBot and AstrBot API wheel verifiers to import proxy factories,
  construct kernel DTOs, and exercise unavailable proxy behavior.
- Run both API wheel verifiers and the example wheel verifiers in ordinary CI,
  not only in the Alpha bundle workflow.
- Provide an installable B7 broker-peer example that completes registration,
  ingress, a lease-bound experimental runtime API call, completion, unregister,
  and shutdown over real ZMQ.
- Update the Native/Cordis plugin example and contributor documentation with
  optional `RuntimeRequirement`/`@runtime` facade usage, provider conformance,
  stable errors, and troubleshooting.

## Boundaries

Stable portable operations remain `event.snapshot`, `event.send`,
`bot.snapshot`, and `bot.send`. Provider-only operations belong in an
`experimental` namespace. Framework SDKs, credentials, and native message
objects remain outside the kernel and portable examples. The historical v5
supervised child-runtime documentation remains available for compatibility but
is not the new bridge development path.

## Exit criteria

- Provider hosts use the shared portable catalog and their manifests expose a
  matching catalog fingerprint.
- Fingerprint mismatch is rejected before a bridge registration is accepted.
- API and example wheel verifiers pass from clean non-project directories with
  no source-tree import dependency.
- A contributor can find the B7 peer, plugin facade, conformance checklist,
  and stable error guidance from the root documentation.
- Full pytest, Ruff, mypy, workspace/example builds, install verifiers, and the
  authorized external workspace pass.

Alpha11 and later provider expansion remain outside this phase.
