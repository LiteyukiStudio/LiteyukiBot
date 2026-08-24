# Releases, PyPI, And Pull Requests

## Recheck Live Release State

Before changing a version or package identity, inspect:

- root and package `pyproject.toml` files plus `uv.lock`;
- `scripts/check_release.py`, `scripts/alpha_release.py`, and the matching
  isolated install verifier;
- `.github/workflows/ci.yaml`, `alpha-release.yaml`, `publish.yml`, and
  `publish-plugins.yaml`;
- `docs/development/releasing.md` and any unexpired release note in
  `docs/tmp/`.

Alpha13 currently builds a signed GitHub Release bundle. Both PyPI workflows
use `--reject-alpha`; do not weaken that boundary incidentally. Package names,
tag patterns, release registry entries, trusted-publisher environments, build
steps, verifiers, docs, and dependency order must change together.

## PyPI Authorization Boundary

Always ask the user immediately before any external PyPI mutation, including:

- creating or claiming a project;
- adding or changing a pending/trusted publisher;
- uploading a distribution or pushing a tag that will upload one;
- yanking, deleting, transferring, or changing project ownership/settings.

A plan, approved package rename, permission to open PRs, or earlier release
discussion is not sufficient authorization. Prepare and validate metadata
locally first, show the exact Project Name, owner, repository, workflow,
environment, and intended operation, then wait for confirmation.

Treat screenshots and temporary requirement notes as dated evidence. Distinguish
owned projects, pending publishers, projects not shown, and proposed names. A
404 or absent screenshot row does not prove that a name is available. Never
rename a distribution solely to bypass an ownership conflict.

## GitHub And Stack PRs

- Conventional Commit subjects and focused PR ownership still apply.
- A stacked PR chain is useful when package extraction creates independently
  reviewable dependencies. Use `$gh-stack-workflow` for Stack operations.
- Discover live state with fetch/prune, current worktrees/branches, remote PR
  heads, checks, approvals, rulesets, and review threads. Do not infer a real
  server-side Stack from base-branch chaining or from a written plan.
- Keep shared metadata in the earliest viable PR and make later PRs depend on
  that explicit base. Rebase/update only after checking current remote state.
- Before an atomic Stack merge, verify that every PR is open, non-draft,
  approved, passing required checks, and has no unresolved review thread.
- Stack permission does not grant PyPI permission. Tags and release workflows
  remain behind the confirmation boundary above.
