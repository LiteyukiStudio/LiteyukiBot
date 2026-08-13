# Benchmarks

`v7-alpha-reference.json` is the recorded pre-Beta performance reference for
kernel startup, event throughput, latency, and peak RSS. It is an auditable
baseline, not an automatic pass/fail threshold.

Generate a local measurement from the repository root:

```bash
uv run python scripts/benchmark_v7.py --output benchmark.json
```

`benchmark.json` is ignored. Only update the tracked reference when its source
environment and measurement rationale are documented in
`docs/performance-v7.md`.

Current CI output uses benchmark schema 2. It contains three independently
started child-process samples per platform and a `summary` with arithmetic mean,
standard deviation, minimum, and maximum. It measures independent-event
concurrency 1/10/100, same-conversation FIFO, successful Action execution, and
function dispatch. It remains an auditable review artifact rather than an
automatic regression gate.
