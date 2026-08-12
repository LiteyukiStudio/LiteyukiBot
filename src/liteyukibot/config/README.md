# Configuration Subsystem

This package owns typed settings, ordered configuration loading, provenance,
redaction, workspace initialization, upgrade recovery material, and encrypted
secret-vault handling.

Configuration precedence and operator behavior are specified in
[`docs/configuration.md`](../../../docs/configuration.md). Keep schema models
strict and diagnostics redacted. New secret values must remain out of IPC,
logs, control responses, and exception text.

Run focused coverage with:

```bash
uv run pytest tests/test_config_v7.py tests/test_config_initializer.py tests/test_config_inspection.py tests/test_config_vault.py tests/test_config_workspace.py
```
