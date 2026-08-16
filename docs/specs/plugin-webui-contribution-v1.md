# Plugin WebUI Contribution v1

- Specification version: `1`
- Applies to: native v7 `PluginManifest.webui` declarations and plugin-owned
  snapshot providers
- Compatibility: pre-stable

## Boundary

A Plugin WebUI contribution is a declarative, host-rendered addition to the
WebUI Plugins workspace. It does not create an HTTP listener, a top-level
workspace, an arbitrary route, or an endpoint owned by the plugin. The host
derives every route as `/plugins/<plugin-id>/<surface-id>`.

`PluginManifest.webui` is optional and leaves the existing plugin API version
at `1`. Its `api_version` is independently negotiated: an unsupported positive
version disables only the contribution, preserves the plugin core, and records
the `unsupported_webui_api` diagnostic.

## Manifest

`WebUiContributionManifest` rejects unknown fields and allows no more than 16
uniquely named surfaces. Each `WebUiSurfaceManifest` rejects unknown fields and
contains:

- a lowercase token `id`, i18n `title_key` and optional `summary_key`;
- one host-approved Lucide icon, a required read capability, and a unique
  operation-ID allowlist;
- an explicit `$schema` value of
  `https://json-schema.org/draft/2020-12/schema`, checked as a Draft 2020-12
  schema when the manifest is created;
- a nonempty declarative component tree.

The host accepts only `navigation`, `status`, `metric`, `detail`, `table`,
`table_row_drawer`, `operation_form`, and `operation_result` components.
Unknown fields, custom code, HTML, Markdown, CSS, custom controls, canvas,
network configuration, polling declarations, and arbitrary icons are outside
this contract. An `operation_form` references exactly one operation ID from its
surface allowlist; the management host later supplies the operation schema,
authorization, confirmation, idempotency, and mutation queue.

All WebUI labels are i18n keys. The contribution declares its owned keys in
`i18n_keys`; every referenced key must be declared and use
`webui.plugin.<plugin-id>.*`. Missing translations render the key. A wrong
namespace or a duplicate active key disables every surface for that plugin
generation with `webui_i18n_namespace` or `webui_i18n_duplicate`; it never
stops plugin core execution.

## Provider Lifecycle And Limits

`PluginHandle.webui_provider` is optional and has one operation:

```python
def snapshot(surface_id: str) -> Mapping[str, object] | Awaitable[Mapping[str, object]]: ...
```

The `PluginManager` registers the provider only after the plugin setup and
`PluginHandle.start` both succeed. It removes the provider before invoking the
plugin stop callback. `webui_generation` changes on every registration or
withdrawal; the daemon-owned WebUI bridge uses that revision to send a browser
reset when it owns such a bridge.

The host checks the surface read capability before calling the provider. Each
call has a 250 ms deadline, must serialize to at most 64 KiB of JSON, must
validate against its declared Draft 2020-12 schema, and may expose at most 200
rows through each declared table path. Timeout, exception, non-JSON value,
schema mismatch, oversized data, and excess rows produce a stable unavailable
state for that surface only. The next refresh retries the provider. Providers
do not receive browser credentials.

## Evidence

The implementation is `src/liteyukibot/plugins.py`. Run:

```bash
uv run ruff check src/liteyukibot/plugins.py tests/test_plugins.py
uv run mypy src/liteyukibot/plugins.py tests/test_plugins.py
uv run pytest tests/test_plugins.py
```
