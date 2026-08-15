# Runtime IPC And Supervision

This package owns the authenticated loopback protocol, child-side
`RuntimeClient`, capability negotiation, event traces, runtime projection, and
supervisor lifecycle. It is the only kernel-side runtime transport.

Do not add direct runtime-to-runtime channels. Keep framing bounded, payloads
JSON-safe, and child capabilities explicit. Public protocol changes require
models, compatibility tests, and the matching versioned specification.

Protocol v5 allows a ready child with `runtime.management.execute` to invoke an
already registered kernel management command. It is capability-gated by the
permission service and is not a shell, handler-registration, or generic RPC
channel.

```bash
uv run pytest tests/test_protocol_v7.py tests/test_runtime_client_v7.py tests/test_runtime_v7.py tests/test_runtime_generations.py tests/test_runtime_projection.py
```
