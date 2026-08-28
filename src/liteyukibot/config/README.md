# Configuration

This package owns immutable schema-7 settings, ordered TOML/JSON/YAML layers,
environment and CLI overrides, provenance inspection, redaction, workspace
initialization and manual upgrade material.

Removed sections fail validation. Secrets are redacted by `config show` and
`config explain`; the configuration layer does not own a credential vault.

Run `uv run pytest tests/test_config_inspection.py tests/test_config_workspace.py`.
