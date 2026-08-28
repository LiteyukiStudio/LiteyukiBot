# Alpha15 Release Procedure

Alpha15 is a signed GitHub Release bundle. It is not uploaded to PyPI. The
release identity is `v7.0.0a15`, and the bundle contains exactly these four
lockstep distributions:

| Component | Distribution | Source |
| --- | --- | --- |
| `root` | `liteyukibot-v7` | `.` |
| `kernel` | `liteyukibot-v7-kernel` | `packages/kernel` |
| `cordis` | `liteyukibot-v7-cordis` | `packages/cordis` |
| `adapter-onebot` | `liteyukibot-v7-adapter-onebot` | `packages/adapter-onebot` |

The canonical identities, tags, dependency pins, verifier commands, and
manifest order live in `scripts/release_registry.py`. All four project
versions and all internal dependency pins must equal `7.0.0a15`.

## Local Qualification

Use CPython 3.14 and uv:

```bash
uv sync --locked --all-packages
uv run liteyuki --workspace tmp/release-workspace init
uv run liteyuki --workspace tmp/release-workspace check
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build --all-packages --out-dir dist/workspace --clear
uv run python -m scripts.run_kernel_install
uv run python -m scripts.run_cordis_install
uv run python -m scripts.run_onebot_adapter_install
uv run python -m scripts.run_tool_install_smoke
```

`uv run python scripts/check_release.py` and
`uv run --group release python -m scripts.alpha_release check-source` must pass
before building the bundle. The CI workflow is the authoritative complete
sequence; the Alpha workflow repeats the source, build, manifest, signature,
offline install, and verification gates.

## Bundle Rules

Build only the four project directories. Generate the canonical manifest and
SBOM, sign `artifacts.manifest.json` with Sigstore, copy the bundle outside the
checkout, and run `scripts.run_alpha_bundle_installs` with staged wheels and
`--no-index`. Do not include old Broker, runtime, NoneBot, Satori, WebUI,
Agent, LYF, native IPC, or example artifacts.

Both PyPI workflows retain `--reject-alpha`; no Alpha tag may publish to PyPI.
Any future stable publication needs matching trusted-publisher configuration,
an exact registry identity, and explicit release review.

## SnowLuma Provenance

The OneBot adapter is an independently written protocol client and does not
bundle SnowLuma source, native addons, or assets. Its README links the external
project and states that LiteyukiBot is not affiliated with or endorsed by it.
If future code copies or derives from SnowLuma, preserve the complete upstream
license and notices separately and obtain any required written permission
before public distribution. Do not package the proprietary native addon.
