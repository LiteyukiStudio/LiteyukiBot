# Workflows

These workflows are the executable CI and publishing contracts for v7.

- `ci.yaml` runs cross-platform quality, four-package builds, and isolated
  installs.
- `docker.yaml` builds and smoke-tests the root image on relevant pull requests and main pushes.
- `publish.yml` releases the root package from stable `v7.*` tags; Alpha tags are excluded.
- `publish-plugins.yaml` releases kernel, Cordis, and adapter-onebot from
  immutable package-specific tags.
- `alpha-release.yaml` creates the signed, no-PyPI Alpha bundle from a
  `v7.0.0a*` tag after staged bundle verification.

Keep tag patterns, trusted-publisher environments, `scripts/check_release.py`,
`scripts/alpha_release.py`, and `docs/development/releasing.md` synchronized.
Never add publishing tokens or weaken isolated wheel verification.
