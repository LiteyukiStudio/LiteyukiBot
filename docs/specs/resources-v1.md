# Resources v1

- Specification version: `1`
- Applies to: native resource providers and resource-language Function support
- Compatibility: current v7 pre-release behavior

Native resource providers declare their content and lifecycle through the
resource package boundary. Resource loading is explicit and does not grant a
plugin access to arbitrary workspace files or kernel internals. Resource
language content is parsed and validated before use; failures are reported as
stable diagnostics.

Every directory, ZIP, and installed package resource root contains a
`manifest-v1.json`. The manifest uses schema `1`, a lexically sorted file list
with path, byte size, and SHA-256 digest, plus a SHA-256 root digest over its
canonical JSON payload. It covers `metadata.yml` and every other resource file;
the manifest does not cover itself. The loader rejects a missing manifest,
unsupported schema, unsafe or duplicate path, unsorted entry, digest mismatch,
or any listed/unlisted file-set mismatch before exposing a catalog.

`liteyuki resource manifest <directory>` writes a manifest only when explicitly
requested. `liteyuki resource verify <directory>` verifies one directory pack.
Workspace configuration and startup never create or update manifests.

The current resource API and Function behavior are separate from the planned
new Function development tooling and any future DSL. New syntax is not part of
this specification.

## Evidence

Run `uv run pytest tests/test_resource_packs.py tests/test_cli_v7.py` and the
owning package tests.
