# Release And Verification Scripts

Scripts here are deterministic command-line checks, not runtime imports. The
Alpha15 release graph is defined in `release_registry.py` and contains only
the four lockstep distributions.

- `check_release.py` validates project identities and release tags.
- `alpha_release.py` validates and generates the signed bundle manifest.
- `run_alpha_bundle_installs.py` verifies every staged target wheel offline.
- `run_kernel_install.py`, `run_cordis_install.py`, and
  `run_onebot_adapter_install.py` exercise isolated package installations.
- `verify_published_install.py` verifies the root wheel and its three internal
  dependencies without importing the checkout.
- `run_tool_install_smoke.py` checks the installed `liteyuki` CLI path.
- `run_tool_install_smoke.py --plugin-index INDEX --plugin-id ID` additionally
  checks indexed plugin installation, local configuration, enable/disable, and
  removal inside a fresh `uv tool` environment.
- `generate_supply_chain.py` produces release supply-chain metadata.

Run from the repository root:

```bash
uv sync --locked --all-packages
uv run python scripts/check_release.py
uv run --group release python -m scripts.alpha_release check-source
uv build --all-packages --out-dir dist/workspace --clear
uv run python -m scripts.run_kernel_install
uv run python -m scripts.run_cordis_install
uv run python -m scripts.run_onebot_adapter_install
```

Scripts must not embed credentials or modify tracked source as a side effect.
