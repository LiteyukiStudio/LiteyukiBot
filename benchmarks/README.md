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
