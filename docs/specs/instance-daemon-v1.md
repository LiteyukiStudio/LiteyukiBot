# Instance Daemon v1

- Specification version: `1`
- Applies to: named-instance daemon lifecycle and authenticated local control
- Compatibility: current v7 pre-release behavior

Each `liteyuki run` daemon owns one named instance, its daemon lock, a local
authenticated descriptor, and exactly one supervised worker. The worker keeps
the data-directory lock and its own runtime control descriptor. Named instances
derive isolated state below `.liteyuki/instances/<name>/`; the default instance
preserves configured storage paths.

Daemon control is loopback-only and authenticated with a random descriptor
token. It may stop or restart its worker and can bound abnormal restart retries.
It never persists decrypted runtime secrets. Development forwarding is opt-in,
authenticated, and limited to explicitly registered development controls.

The daemon is not an HTTP administration API in the current implementation.
The future WebUI bridge is a proposal only and must not be inferred from this
specification.

## Evidence

Run `uv run pytest tests/test_daemon.py tests/test_cli_v7.py`.
