---
name: liteyuki-webui-frontend
description: Build, review, or test LiteyukiBot v7's React/Vite WebUI under webui/ and its packaged static delivery in packages/webui/. Use for UI/UX, shared components, WebUI API views, Vite development, static staging, Playwright visual checks, and WebUI pull requests.
---

# LiteyukiBot WebUI Frontend

## Scope

- The browser app belongs in `webui/`: React, TypeScript, Vite, Tailwind CSS 4,
  shadcn primitives, Playwright tests, and the development launcher.
- The HTTP bridge and wheel packaging belong in `packages/webui/`. Browser code
  consumes the bridge; it does not import daemon internals or execute raw
  management commands.
- `packages/webui/src/liteyukibot_webui/static/` and `webui/dist/` are generated.
  Stage them with `uv run python scripts/stage_webui_assets.py`; do not hand-edit
  or commit generated assets.

## Before Editing

1. Read the changed view, its API model in `webui/src/lib/`, the matching
   Playwright coverage, and the service contract if the request affects data or
   authorization.
2. Check `git status -sb`. Create a focused branch for a functional or visual
   change. Do not open a PR when the user says the work is still exploratory.
3. Treat a screenshot as evidence of the running asset set. Compare its visible
   structure against the current source and stage/build state before blaming CSS
   caching.

## Product Rules

- This is a local operations surface, not a marketing page. Optimize for scanning
  real instance, runtime, plugin, audit, and operation state.
- Render only bridge-derived data in production views. Never restore old mock
  data merely to fill an empty state.
- Keep text purposeful. A title names a view, a status names current state, and
  a description explains a decision, recovery action, high-impact consequence,
  or unfamiliar empty state. Remove labels that merely repeat the title or the
  value beside them.
- Do not put agent prompts, implementation narration, keyboard-shortcut help,
  or other non-user-facing copy in frontend source or i18n catalogs.
- Empty states and errors must state the actual condition and the available
  recovery action. Do not use decorative sample events, runtimes, progress, or
  metrics.
- Do not make initial setup a blocking default route. Put setup instructions in
  a dedicated help surface or an on-demand Runtimes action when that surface is
  implemented.

## Design System

- Reuse existing primitives and local components before adding Tailwind class
  strings. Extract a component when a surface or control has more than one real
  call site, such as `SurfaceCard`, `Sidebar`, or `TopStatusBar`.
- Tailwind is for local composition. Put shared visual behavior in component
  variants or `webui/src/styles.css` semantic classes.
- Use semantic CSS tokens from `:root`; active states, status colors, shadows,
  and surfaces must derive from tokens rather than hard-coded component colors.
  Do not put `var(...)` or hex values in Tailwind class names.
- Keep the locale catalog restricted to actual user-facing UI. The top status
  bar owns the persisted language and theme controls; themes use semantic token
  overrides and must work without per-component hard-coded active colors.
- Resolve `webui.*` text through the authenticated presentation endpoint. The
  endpoint is backed by the kernel `ResourceCatalog`, including enabled plugin
  packs; frontend source may name stable message keys and interpolation values,
  but must not introduce a second translated catalog.
- Theme selection consists of light/dark/system mode plus the Blue, Lavender,
  and Cyan accent groups from `tmp/v7-webui-uiux-design.md`. Keep their paired
  token values in the CSS registry and use the theme reveal controller for
  visual mode changes; reduced-motion users receive an immediate transition.
- Keep the Signal Ledger layout: a white fixed navigation rail, unframed normal
  navigation, one theme-derived active row, elevated content surfaces, and a
  compact top status bar for the current page and live state. On desktop, the
  rail and top bar form one continuous shell with a rounded inner transition;
  the mobile drawer remains an independent bordered surface. Extend the status
  bar for real transfer progress only when that capability exists.
- Use Lucide icons from the installed set. Icon-only controls need an accessible
  name and tooltip. Keep cards at modest radii, preserve desktop/mobile text
  fit, and inspect both layouts for overflow or overlap.
- SeaLantern is a visual reference for restrained elevation and grouping, not a
  dependency or a source of Vue components.

## Data And Security

- Use `WebUiApi` and `projectDashboard`; keep session redemption, CSRF, SSE,
  ticket, authorization, and operation validation server-owned.
- Use structured operation catalog entries and typed input. A browser must not
  expose a raw-command path.
- A WebUI ticket is one-time. `liteyuki web open` opens the default browser and
  consumes the ticket there; do not diagnose a later pasted copy as a CSS or
  transport failure without checking this behavior.

## Development And Verification

```powershell
pnpm --dir webui install --frozen-lockfile
pnpm --dir webui typecheck
pnpm --dir webui build
$env:PLAYWRIGHT_EXECUTABLE_PATH = Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"
pnpm --dir webui test:e2e
uv run --extra webui pytest -q packages/webui/tests
uv build --project packages/webui --out-dir dist/workspace
uv run python scripts/stage_webui_assets.py
```

- Use `pnpm --dir webui run web` for a Vite development instance proxied to a
  real local daemon. Use `scripts/run_webui_daemon.ps1` for package-static
  verification; it prints the actual loopback endpoint.
- For visual work, capture desktop and mobile states with real data or explicit
  API interception. Confirm nonblank render, no horizontal overflow, text fit,
  navigation behavior, and staged static assets.
- Run the narrowest relevant checks while editing, then the commands above for a
  WebUI feature, package boundary, static asset, or launcher change.

## Delivery

- A normal completed change uses a focused PR to `main`, all checks green,
  verified review findings only, then squash merge and branch deletion.
- Keep exploration on its branch when requested. Commit coherent checkpoints if
  asked, but do not create or merge a PR until the user reopens that step.
