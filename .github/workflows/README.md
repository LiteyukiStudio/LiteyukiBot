# Workflows

These workflows are the executable CI and publishing contracts for v7.

- `ci.yaml` runs cross-platform quality, package builds, isolated installs, and
  the NoneBot contract.
- `docker.yaml` builds the root image on relevant pull requests.
- `publish.yml` releases the root package from an immutable `v7.*` tag.
- `publish-plugins.yaml` releases first-party packages from immutable
  package-specific tags.
- `alpha-release.yaml` creates the signed, no-PyPI Alpha bundle from a
  `v7.0.0a*` tag after staged bundle verification.

Keep tag patterns, trusted-publisher environments, `scripts/check_release.py`,
`scripts/alpha_release.py`, and `docs/development/releasing.md` synchronized.
Never add publishing tokens or weaken isolated wheel verification.
