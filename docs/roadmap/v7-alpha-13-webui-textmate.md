# v7 Alpha 13: WebUI and LYF TextMate Extraction

Status: complete as a source milestone. No `v7.0.0a13` GitHub Release was
created; Alpha14 supersedes its source identity.

Alpha13 updates the operator WebUI for the Alpha12 plugin lifecycle and moves
LYF TextMate tokenization into the independently versioned
`LiteyukiStudio/lyf-textmate` repository and `@liteyuki/lyf-textmate` npm
package. The source identity for this stage is `7.0.0a13` / `v7.0.0a13`.

Completion evidence:

- `@liteyuki/lyf-textmate@0.1.0-alpha.13` was published through the
  `LiteyukiStudio/lyf-textmate` GitHub Actions trusted publisher workflow
  `.github/workflows/publish.yml`. npm records SLSA provenance, source
  `gitHead` `fc94c4280fb22e0cc937779734c975e5e0b6e373`, and integrity
  `sha512-8vfqxmjMvJvO3KLctd1Yg4Pjl0lO9hEL4p9C7YxMFD8VEx0YchMk3TM8bRwQ1qyr8gjsb4H0kc0eNxCoEFod7A==`.
- LiteyukiBot commit `62065111b9345b52120ca2d3d3de9fe485aed65b`
  replaced the temporary Git dependency with the exact npm version.
  `webui/package.json` and `webui/pnpm-lock.yaml` both resolve
  `0.1.0-alpha.13`; the lock also retains the registry integrity.
- The typed plugin WebUI and read-only LYF tokenization consumer are merged.
  Remaining architecture and release work moved to the
  [Alpha14 route](v7-alpha-14-baseline.md).

The remainder of this document preserves the implementation plan and its
original sequencing; it is not the current release route.

## Verified starting point

- `webui/` is a private React 19, TypeScript, Vite, and Tailwind application.
  `packages/webui/` owns authenticated loopback transport and packaged static
  delivery.
- The plugin workspace currently displays `topology.plugins`, which represents
  loaded kernel extensions. It does not expose Alpha12 index discovery,
  publisher/license metadata, target bridge generations, or lifecycle state.
- The generic operation catalog already contains install, update, enable,
  disable, uninstall, rollback, and garbage-collection commands. It has no
  typed read-only plugin discovery endpoint, so the WebUI must not scrape CLI
  output or infer state from operation text.
- `GET /api/v1/lyf/resources` already returns bounded read-only resources with
  `grammar: "source.lyf"`, source text, and parser diagnostics.
- `webui/src/features/lyf/lyf-resource-view.tsx` currently renders escaped
  plain text through React `<pre><code>`. There is no TextMate, Oniguruma, or
  syntax-highlighting dependency in `webui/package.json`.

## Goals and non-goals

Alpha13 must:

1. expose typed, bounded, read-only plugin discovery and managed-generation
   state through the daemon-owned WebUI boundary;
2. provide an ergonomic plugin search, review, install, update, state change,
   rollback, uninstall, and cleanup workflow without weakening Alpha12
   confirmation or authorization rules;
3. publish a framework-neutral LYF TextMate package with deterministic grammar,
   tokenization, themes, tests, package exports, and provenance;
4. consume that package in the LiteyukiBot WebUI and preserve the existing
   read-only and diagnostic behavior; and
5. verify frontend performance, memory release, responsive layout,
   accessibility, packaged static delivery, and installability from built
   artifacts.

Alpha13 does not add an LYF editor, execute source from the browser, expose
credentials, turn plugin metadata into trusted content, redesign the portable
Runtime API, or perform Beta qualification. It also does not move
Python LYF parsing or diagnostics into JavaScript.

## Implemented package boundary

`LiteyukiStudio/lyf-textmate` owns the ESM-first, framework-neutral
`@liteyuki/lyf-textmate` package.
Keep React components in LiteyukiBot; the reusable package owns language data
and tokenization rather than application layout.

Use `vscode-textmate` with `vscode-oniguruma` directly. This matches the
requested TextMate boundary and avoids making Shiki's renderer and theme model
part of the public API. The cost is explicit WebAssembly initialization and
worker/bundler testing. Shiki is an acceptable fallback only if a short
prototype proves that direct Oniguruma loading cannot remain portable across
Vite, Node tests, and downstream bundlers.

The first public API should stay small:

```ts
export const LYF_SCOPE_NAME: "source.lyf";
export type LyfToken = { startIndex: number; endIndex: number; scopes: readonly string[] };
export type LyfTokenLine = { text: string; tokens: readonly LyfToken[] };

export function createLyfTokenizer(options?: LyfTokenizerOptions): Promise<LyfTokenizer>;
export function loadLyfGrammar(): Promise<RawGrammar>;
```

`LyfTokenizer.tokenize(source, options)` returns structured lines and scope
ranges. It must not return unsanitized HTML. The WebUI maps known scopes to CSS
tokens and renders text nodes, which keeps source content outside an HTML
injection boundary. Export the grammar JSON and default light/dark token maps
through explicit package exports; do not expose internal engine objects as a
compatibility promise.

The package must define maximum source bytes, line count, line length, and
token count. It must support cancellation or supersession so rapidly changing
resources do not retain obsolete token trees. Cache only the immutable grammar,
Oniguruma engine, and a bounded number of source results; expose `dispose()` for
workers or engine resources that require explicit teardown.

## WebUI contract changes

Add typed daemon/WebUI responses rather than reusing presentation snapshots:

- plugin sources: ID, priority, official/custom identity, cache state, and
  digest, with credential-free URLs only where an operator needs them;
- discovery records: source, bundle ID/version, display name, summary,
  publisher, license, status, runtime kinds, requested capabilities, repository,
  homepage, and exact download bytes;
- managed targets: bridge/runtime ID, kind, support grade, active generation,
  previous generation, enabled bundle set, and restart-required state; and
- lifecycle preview: the exact source digest, selected target, resolved closure,
  publisher/license/security metadata, capabilities, and total input bytes.

All collections need explicit page/query limits and stable error codes. Search
must remain server-side so an 8 MiB index and its parsed object graph are not
kept indefinitely in the browser. Preview and submission must preserve
Alpha12's digest binding; the daemon rejects a stale preview even if the UI is
open. Mutating requests continue through the operation ledger and exact-target
confirmation. The browser never receives artifact bytes, local artifact paths,
environment variables, credentials, or executable load plans.

Replace the current Plugins workspace with two visually distinct views:

- **Discover**: bounded search, source/status/runtime filters, metadata review,
  yanked-state visibility, target selection, and install preview;
- **Managed**: target selector, active/previous generation, bundle state,
  update/enable/disable/rollback/uninstall actions, restart state, and explicit
  garbage-collection evidence.

Keep loaded kernel extensions in Topology or label them explicitly as kernel
extensions. Do not merge them into managed bridge generations merely because
both are called plugins.

The LYF workspace should lazy-load `@liteyuki/lyf-textmate`, tokenize only the
selected resource, display a stable loading/error/plain-text fallback, retain
diagnostics, and avoid layout movement when tokens arrive. Rendering remains
read-only and uses React text children rather than `dangerouslySetInnerHTML`.

## Implementation order

### Phase 0: open the stage

1. Record `npm whoami` and `npm access list packages @liteyuki`; when scope
   access is unavailable, use the reviewed standalone Git commit and do not
   publish an npm artifact.
2. Confirm the Alpha12 main and official-index work is merged and record the
   exact baseline commits.
3. Create the Alpha13 branch and only then bump lockstep metadata to
   `7.0.0a13`.

Exit: package ownership and source baselines are recorded; no guessed npm
permissions or release identities remain.

### Phase 1: extract and publish LYF TextMate

1. Create the standalone repository with license, security policy, CODEOWNERS,
   provenance-enabled npm publication, protected `main`, and pinned CI actions.
2. Move or author the canonical `source.lyf` TextMate grammar against the
   maintained LYF language documents and diagnostic fixtures.
3. Implement the bounded tokenizer API, explicit WASM initialization, theme
   token maps, disposal, and framework-neutral tests.
4. Test Node ESM import, Vite browser bundling, package tarball contents,
   grammar snapshots, malformed input, adversarial long lines, cancellation,
   repeated initialization, and retained-memory behavior.
5. Build an immutable tarball and install it in a clean consumer. When scope
   access is available, publish an immutable prerelease and repeat the same
   consumer check against the exact npm version.

Exit: the public package can tokenize representative LYF in Node tests and a
browser build without repository-relative assets or unbounded caches.

### Phase 2: add typed plugin WebUI APIs

1. Define JSON-safe response models and limits in the daemon/WebUI boundary.
2. Implement search, source, target, generation, and preview reads by reusing
   Alpha12 stores and installation service contracts.
3. Route mutations through the existing operation catalog and ledger; add a
   new operation only when the existing argument schema cannot express the
   digest-bound preview contract truthfully.
4. Add authorization, CSRF, stale-digest, yanked bundle, invalid target,
   pagination, redaction, and maximum-size tests.

Exit: the frontend no longer needs CLI text parsing or topology inference, and
every write preserves daemon ownership and auditable confirmation.

### Phase 3: update the React WebUI

1. Add typed API models/services and keep discovery state scoped to the Plugins
   workspace rather than the application root.
2. Build Discover and Managed views with explicit loading, empty, stale,
   restart-required, rollback-available, yanked, error, and success states.
3. Integrate the fixed Git commit through a lazy chunk during this stage;
   switch to the exact published `@liteyuki/lyf-textmate` version after npm
   scope access is available. Keep plain-text fallback and diagnostics usable
   if tokenization fails.
4. Update localization keys, keyboard/focus behavior, narrow/mobile layout,
   light/dark/high-contrast token colors, and reduced-motion behavior.
5. Measure initial bundle size, lazy LYF chunk size, repeated search memory,
   resource-switch token memory, and DOM/token counts before and after.

Exit: core dashboard startup does not download the TextMate engine, repeated
search/resource switching releases obsolete data, and all normal workflows are
usable without horizontal page overflow or inaccessible icon-only actions.

### Phase 4: release proof

1. Build and pack the npm package, WebUI SPA, Python WebUI wheel, and Alpha13
   workspace bundle from clean checkouts.
2. Run the packaged WebUI against a real daemon in a temporary workspace.
3. Install the Alpha12 reference NoneBot plugin through the UI, verify restart,
   disable/enable, rollback, uninstall, and cleanup, then verify LYF rendering
   and diagnostic fallback.
4. Run the dependency audits, install verifiers, full Python gates, WebUI tests,
   and performance/residency checks.

Exit: built artifacts, rather than source aliases or linked packages, pass the
complete operator workflow.

## Required validation

At minimum, run:

```text
pnpm --dir webui install --frozen-lockfile
pnpm --dir webui typecheck
pnpm --dir webui build
pnpm --dir webui test:e2e
pnpm --dir webui audit --prod
uv run pytest packages/webui/tests
uv run python -m scripts.run_webui_install
uv run ruff check src tests scripts examples packages
uv run mypy
uv run pytest
uv build --all-packages --out-dir dist/workspace --clear
```

The standalone npm repository additionally needs unit tests, browser bundler
tests, `npm pack --dry-run`, a clean tarball-consumer test, production audit,
provenance verification, and a memory/residency workload. Capture Playwright
screenshots at desktop and mobile widths for Plugins and LYF states and inspect
them for clipping, overlap, blank code panes, and unreadable token contrast.

## Completion boundary

The standalone package, typed backend contract, WebUI integration, and exact
npm consumer landed as separate ownership changes. The package is not vendored
into `webui/` and the consumer does not depend on a floating npm tag. Alpha13
did not create a signed `v7.0.0a13` GitHub Release; opening the Alpha14 source
and release graph superseded that artifact step.
