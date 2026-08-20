# v7 Alpha 6: Independent Agent Bridge

> **Planned implementation contract.** This document records the agreed Agent
> Alpha boundary. It does not claim a production-safe Agent, RAG, or sandbox.

Alpha 6 replaces the historical Agent runtime/plugin with separate `agent` and
`agent-sandbox` broker bridges. It remains experimental and starts only after
Alpha 5 is merged.

## Release and bridge boundary

The lockstep set advances to `7.0.0a6`. Every independent first-party package
is rebuilt for this Alpha and exactly depends on `liteyukibot-v7==7.0.0a6`.
The Agent package publishes both bridge definitions. `agent` is limited and
subscribes to configured message topic patterns; `agent-sandbox` is limited,
has no event subscriptions, and owns configured agent-specific Tool IDs.

The Agent uses vault-resolved OpenAI-compatible provider credentials, bounded
per-source/bot/conversation SQLite history, configured model/event/tool-round
timeouts, and one final `message.send` reply per event.

## Tool discovery and execution

Agent Resolver builds a static, broker-validated configured tool universe.
The model initially receives at most eight schemas including catalog search.
Search returns at most eight additional declarations and activates at most 32
schemas in one event. The catalog search tool is local; every selected external
tool still invokes the frozen broker Tool RPC.

The Agent bridge is limited and builds a read-only Permissions v2 policy from
the same configuration, so calling and providing hosts both authorize the
original context. History persists user text, final assistant text, and only
redacted/truncated Tool summaries; it never persists raw tool input/output,
RAG chunks, provider secrets, or complete provider transcripts.

`agent-sandbox` starts a fresh native subprocess for every invocation. It
provides read/write, HTTPS, and command primitives governed by configured file
roots, command allowlists, wall/output limits, cancellation, and crash
handling. CPU/memory hard limits remain platform-dependent and are not a
hostile-code containment claim. HTTPS is permitted by default; loopback,
private ranges, nonstandard ports, and non-HTTPS traffic require explicit
policy.

Third-party sandbox tools may be discovered by worker entry point. Native
subprocess execution is not a hostile-code security boundary: policy constrains
built-in primitives but cannot guarantee containment of malicious Python.

## Experimental RAG

Configured local document directories are content-hash indexed into SQLite.
Startup incrementally rechunks changed files and removes chunks for deleted
files. OpenAI-compatible embeddings feed cosine retrieval; identity reranking
is the reference replaceable rerank provider. Citation emission is configurable
and defaults off.

Tests cover provider fakes, search bounds, catalog-owner mismatch,
caller/provider authorization, final-only replies, history redaction, RAG
updates/deletions, optional citations, worker timeout/cancel/crash, built-in
allowlists, third-party limitation reporting, and Agent-to-business-Tool flows.

Agent quality, provider breadth, RAG quality, and third-party containment are
not Alpha stability claims.
