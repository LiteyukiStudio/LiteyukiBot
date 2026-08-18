# Extension API v2

- Specification version: `2`
- Applies to: Alpha 2 Native and Cordis extension declarations
- Compatibility: v1 values are rejected; `PluginManifest` and
  `PluginDefinition` are source aliases that construct v2 values.

`ExtensionManifest(api_version=2)` is the shared declaration for identity,
service/resource declarations, requested capabilities, coexistence, and Tool
declarations. Tool IDs are globally namespaced by the extension ID. Input and
output schemas use Draft 2020-12 and are checked at declaration time.

Native extensions are limited. Cordis extensions are full unless the
administrator lists their ID under `[cordis.access]`, where the only accepted
override is `limited`. An extension cannot grant or elevate its own access.
`stable-first` is release governance and is not an API or authorization value.

The v1 aliases do not restore v1 authorization semantics: the only accepted
manifest API version is `2`. Host activation must validate every requested
capability against the Permissions v2 ceiling before setup or Scope activation.
Native setup and Cordis Scope activation must register exactly one handler for
each declared Tool before the kernel bridge registers its immutable manifest.

Evidence: `tests/test_alpha2_contracts.py`, `tests/test_plugins.py`,
`tests/test_cordis_host.py`.
