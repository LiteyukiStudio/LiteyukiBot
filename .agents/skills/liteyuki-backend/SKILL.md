---
name: liteyuki-backend
description: Build, review, refactor, or release LiteyukiBot v7 backend code and first-party Python packages. Use for kernel, Broker, daemon, Cordis, plugins, adapters, runtime migration, package boundaries, backend contracts, documentation governance, CI, or release work in this repository. Do not use for WebUI-only frontend work.
---

# LiteyukiBot Backend

## Start With Evidence

1. Run `git status -sb` and inspect the code, tests, metadata, workflow, and
   canonical document that own the requested boundary.
2. Keep the checked Alpha13 implementation separate from the approved
   Alpha14/Alpha15 direction. Never describe a planned split, rename, removal,
   freeze gate, or release as already implemented.
3. Run the smallest relevant validation while editing, then expand validation
   according to the changed ownership boundary.

Read only the references needed for the task:

- [current-state.md](references/current-state.md): always read before making an
  architecture, ownership, compatibility, or migration claim.
- [architecture-direction.md](references/architecture-direction.md): read for
  Alpha14/Alpha15 work, package extraction, Cordis, Native, Broker, security,
  observability, WebUI scope, or Beta readiness.
- [engineering-workflow.md](references/engineering-workflow.md): read before
  backend edits, package-boundary changes, testing, documentation work, or
  multi-agent execution.
- [release-and-prs.md](references/release-and-prs.md): read before version,
  package identity, release workflow, GitHub Stack, tag, or PyPI work.

For WebUI-only React/Vite work, use `$liteyuki-webui-frontend`. For benchmark
semantics or performance artifacts, also use `$benchmark-tests`.

## Non-Negotiable Boundaries

- The product direction is Liteyuki-first. Do not add compatibility with an
  external ecosystem merely to acquire users or feedback.
- Treat Cordis plugins as trusted in-process Python, never as a malicious-code
  sandbox. Broker is the cross-process authority boundary.
- Kernel changes must serve protocol-neutral contracts or genuinely shared
  interfaces. Move concrete business behavior to its owning package.
- WebUI is feature-frozen during Alpha14/Alpha15; allow fixes and maintenance,
  not new management domains or product expansion.
- Any PyPI mutation, trusted-publisher change, project creation, upload, yank,
  or ownership change requires immediate user confirmation, even if the wider
  task or a release plan was previously approved.
