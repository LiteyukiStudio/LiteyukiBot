# LiteyukiBot v7 Performance Reference

## Published Install Contract

CI installs the newest published `liteyukibot-v7` in the
`>=7.0.0a2,<8` release window from PyPI in an isolated uv environment on
Ubuntu, Windows, and macOS. It verifies that distribution metadata and the
`liteyukibot` kernel namespace report the same version. The separately released
v6 runtime has its own isolated-install verifier for the `liteyuki`
compatibility namespace.
The check does not use the repository virtual environment or install the source
checkout, and remains valid before and after the a3 upload.

Run the same contract locally with:

```bash
uv run --no-project --python 3.14 python scripts/run_isolated_install.py \
  --with "liteyukibot-v7>=7.0.0a2,<8" \
  --verifier scripts/verify_published_install.py
```

## Alpha Reference

The first reference set is stored in
`benchmarks/v7-alpha-reference.json`. Each value is the median of three samples
from successful `v7` push workflows after PRs #96, #97, and #98. All samples
used CPython 3.14.5 and 5,000 independently ordered events.

| Runner | Startup ms | Events/s | Median latency ms | p95 latency ms | Peak RSS MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| `macos-latest` | 2.913 | 31,690 | 1.776 | 2.359 | 46.3 |
| `ubuntu-latest` | 2.333 | 24,400 | 2.311 | 2.665 | 51.5 |
| `windows-latest` | 6.916 | 18,011 | 3.337 | 4.532 | 45.6 |

Source workflow runs:

- [31300636600](https://github.com/LiteyukiStudio/LiteyukiBot/actions/runs/31300636600)
- [31300865414](https://github.com/LiteyukiStudio/LiteyukiBot/actions/runs/31300865414)
- [31301376697](https://github.com/LiteyukiStudio/LiteyukiBot/actions/runs/31301376697)

## Interpretation

This alpha reference is auditable but not an automatic performance gate.
GitHub-hosted runner load remains visible in the individual artifacts; for
example, one macOS startup sample was 20.8 ms while the other two were below
3 ms. Median aggregation limits a single outlier without hiding the raw runs.

After the first stable v7 release, replace this file with a stable reference
captured from three clean runs per platform. A regression review is required
when startup, latency, or RSS rises by more than 20%, or throughput falls by more
than 20%. The comparison must use the same Python minor version, event count,
runner architecture, and benchmark schema.

## Schema 2 Workloads

Current CI artifacts use schema 2. Each platform starts three separate Python
processes and records every raw sample plus arithmetic mean, standard deviation,
minimum, and maximum. Separate processes keep startup, tracemalloc, and peak
RSS measurements independent.

The event matrix contains independently ordered conversations submitted at
concurrency 1, 10, and 100; a single-conversation FIFO workload; and a workload
where every event performs one successful Action. Every workload uses 5,000
events. Function catalog setup, first call, and hot calls remain included.

Schema 1 alpha references are historical and cannot be compared mechanically to
schema 2 because the workload set and aggregation shape changed. Schema 2
artifacts are reviewed manually: GitHub-hosted runner variance must be examined
through raw samples and dispersion before attributing a change to the code.

## Beta 7 Runtime Profiles

Schema 2 now supports two explicit profiles. `bare` is the default and starts
the kernel with no extensions. `installed-first-party` resolves the installed
LiteyukiBot first-party distributions once in the parent process, records a
stable distribution/version and Native/Cordis entry-point manifest, and passes
that exact JSON snapshot to every independent sample child. It does not import
optional hosts while discovering metadata. A Cordis entry point is marked
disabled when no unambiguous Cordis host is installed; the package is still
present in the manifest and is not silently treated as exercised.

The stable qualification set should publish two artifacts using the same
schema-2 event and function matrix:

```bash
uv run python scripts/benchmark_v7.py --profile bare --samples 3 --output benchmark-bare.json
uv run python scripts/benchmark_v7.py --profile installed-first-party --samples 3 --output benchmark-installed-first-party.json
```

The second artifact represents the actual installed first-party workspace, not
a hand-maintained package list. Compare only artifacts whose profile and
resolved `extension_manifest` match. The profile artifacts are evidence for
manual review; they are not automatic CI performance gates. This document does
not define the later 72-hour soak or the full-workspace theoretical benchmark.

## Alpha11 Resident-State Workloads

Schema 2 additionally records EventBus and Broker residency under 20,000
unique-conversation events carrying independent 1 KiB payloads. EventBus must
drain outstanding work and per-key queues/workers to zero. Broker uses its
4,096-event and 16 MiB retained-content capacities and must evict older
terminal records while removing delivery indices and ordering lanes.

Each owner remains alive through measurement. Samples record current RSS before
and after the workload, RSS delta, and GC-after-workload `tracemalloc` retained
and peak bytes. These numbers expose the cost of bounded retention; they do not
establish a universal byte threshold because allocator and platform behavior
differs. Compare artifacts only when resident event count, payload bytes,
profile manifest, Python minor version, and platform match.
