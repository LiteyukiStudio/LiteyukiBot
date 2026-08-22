# v7 Alpha 11: Security, Quality, and Residency Qualification

Alpha11 qualifies the existing Alpha10 ecosystem surface. It does not add a
provider, portable operation, plugin host, or compatibility layer. Its purpose
is to remove known dependency and resource-boundary risks, reduce measured
complexity in high-risk paths, and prove that long-running bounded state does
not grow with total historical traffic.

## Security gate

- Runtime distributions that enable HTTP/2 require `h2>=4.4.1,<5` so the
  workspace and independently installed bridge wheels exclude the known
  request-smuggling releases.
- CI audits the complete Python environment and WebUI production dependency
  graph after locked installation.
- Plugin ZIP extraction verifies the cached content digest and enforces 10,000
  members, 256 MiB per member, and 1 GiB total extracted content. Path
  traversal and symbolic links remain rejected.
- LYIP rejects payloads above 8 MiB and encoded frames above 12 MiB at object,
  codec, and ZMQ socket boundaries.
- Broker terminal diagnostics apply both a 4,096-record limit and a configurable
  16 MiB retained-content budget.
- Native plugins and third-party Agent worker functions remain trusted code;
  Alpha11 does not claim hostile-code containment.

## Quantitative source-quality gate

The review baseline is collected separately for `src`, `packages`, and
`webui`; generated WebUI assets are excluded. The initial Alpha11 scores are
76.36, 84.77, and 96.29 respectively. Scores route review effort but do not
replace tests or justify comment padding.

Refactoring is limited to behavior-protected hotspots. A selected hotspot must
reduce its reported complexity or risk index without changing public errors,
ordering, authorization, or wire behavior. Comments and docstrings are added
only for non-obvious state, security, static-evaluation, or measurement
contracts. Alpha11 records the before/after scores and does not accept a lower
hotspot score. Aggregate scores are reported with an explanation when new
security branches change the scanned surface; they are not improved with
comment padding.

The first targets are command token binding, LYF static preflight, and local
control authentication/dispatch. CLI, daemon, broker, and adapter hotspots
remain candidates only when focused tests protect the edited behavior.

## Resident-state benchmark

Benchmark schema 2 retains one fresh Python process per sample and the existing
event/function matrix. Alpha11 adds a resident-state group with explicit
`resident_event_count` and `resident_payload_bytes` compatibility keys.

Each sample processes 20,000 unique-conversation events with an independent
1 KiB payload through:

- EventBus churn, which must finish with zero outstanding events, key queues,
  key workers, and ingress entries;
- Broker delivery settlement using the production 4,096-event and 16 MiB
  terminal-content capacities, which must finish with zero active events,
  delivery indices, and lanes while staying inside both limits.

Both workloads report elapsed time, throughput, RSS before/after/delta, and
GC-after-workload `tracemalloc` retained/peak bytes while the owning EventBus or
BrokerLedger remains alive. The retained owner is essential: measuring after
destruction would test cleanup, not long-running cache residency.

CI publishes three independent samples for both `bare` and
`installed-first-party` profiles on Linux, macOS, and Windows. The installed
profile prefers Cordis for a dual-host extension when one unambiguous Cordis
host is present; the Native entry remains in the manifest but disabled.

## Ecosystem governance gates

The default official plugin index currently has no live public repository.
Before an Alpha11 release advertises plugin-store discovery, the index endpoint
must be available and its authenticity/update policy documented. The custom
`LicenseRef-LSO` terms also require a maintainer decision before broader
third-party or corporate adoption; this qualification does not rewrite legal
terms implicitly.

## Exit criteria

- `pip-audit` and `pnpm audit --prod` report no known vulnerabilities in the
  locked qualification environment.
- ZIP member-count and extracted-size rejection tests pass.
- Selected `fuck-u-code` hotspots improve quantitatively, all focused behavior
  tests pass, and the three subsystem scans do not regress.
- Benchmark schema, child invocation, aggregation, profile selection, platform
  memory paths, and resident-state invariants have deterministic tests.
- Three-sample `bare` and `installed-first-party` artifacts complete locally
  and in CI; raw samples and dispersion remain available for manual review.
- Ruff, strict mypy, full pytest, workspace builds, install verifiers, and
  release identity checks pass.

The 72-hour soak, a hostile plugin sandbox, distributed delivery, and automatic
performance pass/fail thresholds remain outside Alpha11.

## Local qualification evidence

The Alpha11 implementation pass on Windows 11 and CPython 3.14.3 produced:

| Scope | Initial score | Final score | Decisive hotspot change |
| --- | ---: | ---: | --- |
| Kernel `src` | 76.36 | 76.19 | Broker routing 31.58 to 31.48; plugin store 24.36 to 23.72 |
| Non-generated `packages` | 84.77 | 84.85 | command parsing 27.71 to 16.72 |
| Functions source | 78.90 | 79.00 | preflight 39.94 to 38.30 |
| WebUI | 96.29 | 96.29 | unchanged |

The kernel aggregate decrease is the measured cost of adding LYIP frame and
Broker retained-content branches. The edited security hotspots improved, so no
comments or unrelated refactors were added to manufacture a higher total.

The count-only Broker baseline retained 16,384 records after 20,000 events and
increased RSS by 125.31 MiB in one sample. Adding only a 16 MiB content budget
reduced that to 86.31 MiB. The final 4,096-record plus 16 MiB design averaged
28.32 MiB RSS delta and 17.00 MiB retained Python allocations across three
bare samples. It retained 4,096 records containing 5.73 MiB of measured wire
content; active events, delivery indices, and ordering lanes were all zero.

| Three-sample profile | Startup mean | EventBus RSS delta | Broker RSS delta | Installed entries |
| --- | ---: | ---: | ---: | ---: |
| `bare` | 266.63 ms | 0.46 MiB | 28.32 MiB | 0 |
| `installed-first-party` | 602.48 ms | 0.39 MiB | 28.13 MiB | 22 |

OSV-backed `pip-audit` and `pnpm audit --prod` reported no known
vulnerabilities. Ruff, strict mypy over 322 source files, 751 passed tests with
11 environment-dependent skips, NoneBot, AstrBot, and WebUI install verifiers,
and the 22-package workspace build completed successfully. `liteyuki check`
requires a local `liteyuki.toml`; this checkout intentionally contains only the
example configuration, and CI does not use that command as a repository gate.

### Documentation and post-documentation qualification

The production Python documentation gate covers 184 source files, 531 classes,
and 2,240 callables, including nested and private helpers. Public WebUI exports
and `WebUiApi` methods additionally carry JSDoc. Security-sensitive boundaries
explain the accepted risk, controlling checks, and why the capability remains
available; longer rationale lives in `docs/security/trusted-boundaries.md`.

`fuck-u-code` counts Python docstring lines as file length but does not recognize
them as comments. The direct post-documentation scores therefore fell to 74.19
for `src` and 82.80 for non-generated `packages`, which is a measurement artifact
rather than added control flow. An AST-derived temporary mirror removed only
docstring statements before rescanning, preserving signatures and executable
control flow.
That structural scan scored 76.10 for `src`, 84.86 for non-generated `packages`,
and 97.92 for the WebUI. Broker routing's hotspot index improved further from
31.48 to 31.43 after terminal-limit evaluation and secondary-index eviction were
split into focused helpers. The temporary mirror and reports remain outside the
repository under `F:\tmp\LiteyukiBot-alpha11`.

The complete three-sample benchmark was repeated after documentation expansion
to detect import and resident-memory cost:

| Post-documentation profile | Startup mean | Peak RSS | EventBus RSS delta | Broker RSS delta |
| --- | ---: | ---: | ---: | ---: |
| `bare` | 276.72 ms | 90.57 MiB | 0.24 MiB | 28.44 MiB |
| `installed-first-party` | 473.33 ms | 92.06 MiB | 0.61 MiB | 28.60 MiB |

Compared with the pre-documentation run, peak RSS increased by 0.18 MiB for
`bare` and 0.28 MiB for `installed-first-party`. Broker retained Python
allocations remained exactly 17,827,904 bytes in every sample, with 4,096
terminal records, 5.73 MiB of retained wire content, and zero active events,
delivery indices, or lanes. Throughput moved in both directions across profiles,
so the run does not show a systematic performance regression attributable to
the documentation expansion.
