# ADR 0004: Freeze Configuration Precedence And Error Taxonomy

- Status: Accepted
- Date: 2026-08-09

## Context

Configuration is supplied by files, environment variables, and CLI overrides.
Plugins and operators need deterministic precedence and diagnostics that do not
echo secret values. Runtime and plugin boundaries also need predictable failure
categories.

## Decision

`load_settings()` produces one immutable `AppSettings` snapshot. The precedence
order, from lowest to highest, is:

1. Pydantic model defaults.
2. Includes declared by the primary file, in list order; an included file applies
   its own includes before its own values.
3. Values in the primary file.
4. Repeated CLI `--config` files, in command-line order, each with the same
   include-before-own-values rule.
5. `LITEYUKI__SECTION__FIELD` environment values.
6. CLI `--set section.field=JSON_VALUE` overrides.

Mappings deep-merge. Scalars and arrays replace earlier values. Paths declared
in a configuration file resolve relative to that file; paths supplied through
environment or CLI layers resolve relative to the current working directory.
Duplicate includes, include cycles, malformed documents, unsupported formats,
invalid override syntax, and unknown model fields are configuration errors.

Configuration errors are aggregated as `ConfigurationError.issues`, a tuple of
`ConfigIssue(source, message, location)`. Diagnostics identify source and field
location but never include a supplied secret value.

The framework error taxonomy is:

| Type | Boundary |
| --- | --- |
| `ConfigurationError` | Loading or validating settings. |
| `PluginError` | Plugin discovery, manifest coercion, or setup. |
| `ServiceError` | Undeclared, missing, or conflicting service use. |
| `RuntimeProtocolError` | Invalid local child-runtime frame or message. |
| `LegacyUnsupportedError` | A v6 API outside the compatibility contract. |
| `ControlError` | Invalid or unavailable authenticated local CLI control channel. |

`ActionResult`, `DispatchResult`, and `HandlerFailure` represent expected data
plane outcomes and are not exception replacements. Lifecycle state violations
remain `RuntimeError` until a public lifecycle-specific error type is introduced
in a future major API.

## Consequences

Operators can reproduce an effective configuration from its ordered sources.
Plugins receive a stable read-only configuration view. Future precedence changes
or error reclassification require a major configuration/API version decision and
a migration note.
