---
name: benchmark-tests
description: Maintain LiteyukiBot v7 performance benchmarks and their deterministic tests. Use for benchmark changes, performance-path changes, CI baseline artifacts, workload design, or benchmark regression review in this repository.
---

# Benchmark Tests

## Workflow

1. Read `scripts/benchmark_v7.py`, `tests/test_benchmark_v7.py`, and
   `docs/performance-v7.md` before changing metric semantics.
2. Preserve schema 2: the parent process launches independent `--sample` child
   processes and aggregates raw samples with mean, standard deviation, minimum,
   and maximum. Do not collect repeated samples in one interpreter.
3. Keep the fixed event matrix: independent conversations at submission
   concurrency 1/10/100, same-conversation FIFO, and one successful Action per
   event. Keep function catalog setup, first call, and hot-call measurements.
4. Add deterministic tests for workload behavior, result schema, child-process
   invocation, aggregation compatibility, CLI validation, and platform memory
   paths. Do not assert elapsed-time thresholds.
5. Run `uv run pytest tests/test_benchmark_v7.py`, then the repository quality
   commands. Generate a local artifact with:

```bash
uv run python scripts/benchmark_v7.py --samples 3 --output benchmark.json
```

## Review Rules

- Treat CI artifacts as evidence for manual review, never as automatic
  pass/fail performance gates on shared runners.
- Compare only artifacts with the same schema, Python minor version, event
  count, and workload configuration.
- Preserve raw samples and dispersion. Do not update a tracked reference from
  one run or hide an outlier in a summary-only artifact.
- Keep schema 1 alpha references historical; schema 2 workloads are not
  mechanically comparable to them.
