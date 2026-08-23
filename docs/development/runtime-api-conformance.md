# Runtime API and provider conformance

This guide is the Alpha10.2 contributor gate for the B7 broker bridge and the
Native/Cordis runtime facade. Alpha11 provider expansion is outside this page.

## Portable catalog

Runtime API v1.2 has exactly four stable portable operations:

| Operation | Capability | Result |
| --- | --- | --- |
| `event.snapshot` | `runtime.<kind>.event.snapshot` | `EventSnapshot` |
| `event.send` | `runtime.<kind>.event.send` | `SendResult` |
| `bot.snapshot` | `runtime.<kind>.bot.snapshot` | `BotSnapshot` |
| `bot.send` | `runtime.<kind>.bot.send` | `SendResult` |

Use `portable_runtime_api_catalog(runtime_kind)` from the kernel broker API to
bind this catalog to a provider. Do not duplicate its schemas in a provider
host. Every non-empty `BridgeManifest.runtime_apis` catalog has a deterministic
SHA-256 `runtime_api_fingerprint`; a supplied fingerprint must match the
declarations exactly.

Provider-specific values belong under a namespace such as
`extensions["astrbot"]`. Stable portable consumers must not depend on those
values. New provider-only operations use an `experimental` namespace until a
future contract explicitly promotes them.

## Plugin declaration

The decorator binding and manifest requirement must agree exactly:

```python
from typing import Any

from liteyukibot import RuntimeRequirement, runtime


requirements = (
    RuntimeRequirement(
        runtime="astrbot",
        api="event",
        version="^1.2",
        operations=("snapshot",),
        optional=True,
        bridge_id="astrbot-prod",
    ),
)


@runtime(
    "astrbot",
    api="event",
    version="^1.2",
    optional=True,
    as_="astrbot",
    bridge_id="astrbot-prod",
)
async def handler(event: object, *, astrbot: Any) -> None:
    if not astrbot.available:
        return
    snapshot = getattr(astrbot, "snapshot", None)
    if callable(snapshot):
        await snapshot()
```

Optional providers must treat `available == False` and `RuntimeUnavailable` as
normal paths. Required providers fail registration when the declared runtime
requirement cannot be resolved. Provider send failures and invalid results
must remain stable `RUNTIME_*` errors; do not leak framework exception types.
Runtime requirements also contribute activation capabilities, so the host's
Permission v2 ceiling must explicitly allow the requested runtime capability.

## Provider checklist

- Keep framework imports and native conversion inside the provider package.
- Bind the configured bridge ID into runtime identity and source event IDs.
- Use `BridgeClient` and retain the broker delivery lease until completion.
- Declare only owned subscriptions, action resources, controls, tools, and
  runtime APIs in the manifest.
- Use the kernel portable catalog helper for the four stable operations.
- Keep provider values in a named extension namespace.
- Reject cross-bot calls and return bounded unavailable, invalid-argument,
  invalid-result, and send-failure codes.
- Add non-default bridge ID, disconnect, duplicate source ID, and wheel import
  tests.
- Run the full repository checks and the package's isolated wheel verifier.

## Release verification

Build from the repository root, then verify from a clean non-project directory:

```bash
uv build --all-packages --out-dir dist/workspace --clear
uv build --project examples/broker-peer --out-dir dist/examples
uv run python scripts/run_isolated_install.py \
  --with dist/workspace/liteyukibot_v7-7.0.0a12-py3-none-any.whl \
  --with dist/workspace/liteyukibot_v7_runtime_nonebot_api-7.0.0a12-py3-none-any.whl \
  --verifier scripts/verify_nonebot_api_install.py \
  -- --expected-version 7.0.0a12
uv run python scripts/run_isolated_install.py \
  --with dist/workspace/liteyukibot_v7-7.0.0a12-py3-none-any.whl \
  --with dist/examples/liteyukibot_example_broker_peer-0.1.0-py3-none-any.whl \
  --verifier scripts/verify_broker_peer_example.py
```

The AstrBot API verifier uses the analogous AstrBot wheel. A verifier must
not succeed because `src/` is on `PYTHONPATH`; `run_isolated_install.py`
removes project environment variables before starting it.

## Troubleshooting

- `manifest_mismatch`: compare configured bridge access, subscriptions,
  action resources, and the catalog fingerprint; the broker configuration is
  authoritative.
- `RUNTIME_API_NOT_REGISTERED`: confirm the requested runtime kind, API ID,
  version range, and active delivery lease.
- `RUNTIME_API_INVALID_ARGUMENTS`: validate against the declaration's Draft
  2020-12 input schema before calling the provider.
- `RUNTIME_API_INVALID_RESULT`: the provider returned a value outside its
  declared output schema or typed DTO.
- `RuntimeUnavailable`: the optional facade has no compatible provider or the
  selected `bridge_id` is offline; do not turn this into a successful empty
  result.
