# GitHub Automation

`workflows/` contains CI, Docker build validation, and PyPI Trusted Publishing
workflows for the `v7` branch and package-specific immutable tags.

- `ci.yaml` is the cross-platform quality and installation matrix.
- `docker.yaml` validates the root image for relevant pull requests.
- `publish.yml` publishes the kernel distribution from `v7.*` tags.
- `publish-plugins.yaml` publishes first-party packages from package-specific
  tags.

Keep workflow changes synchronized with `scripts/check_release.py` and
`docs/development/releasing.md`. Do not weaken isolated-install verification or
replace Trusted Publishing with repository secrets.
