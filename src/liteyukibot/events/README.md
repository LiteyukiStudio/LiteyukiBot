# Event And Action Models

This package owns frozen, JSON-safe portable Event and Action models and the
bounded EventBus. It must not import framework SDK types or use adapter-specific
objects as public values.

Changes to envelope fields, validation, ordering, or action routing require the
matching ADR and focused tests. See
[`docs/adr/0001-event-and-action-contracts.md`](../../../docs/adr/0001-event-and-action-contracts.md).

```bash
uv run pytest tests/test_events_v7.py tests/test_app_v7.py
```
