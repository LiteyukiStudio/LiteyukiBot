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
