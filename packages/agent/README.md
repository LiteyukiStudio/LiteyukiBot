# LiteyukiBot Agent Bridges

This package provides the experimental `agent` and `agent-sandbox` Broker
bridges. It is not a child Runtime, native plugin, or replacement for a
framework bridge.

The `agent` bridge receives configured message topics through a limited Broker
manifest and sends at most one final `message.send` action back through the
source bridge's active delivery. OpenAI-compatible provider credentials are
resolved by the launcher from the vault-backed bridge options. Conversation
history is bounded SQLite data keyed by source bridge, bot, and conversation.

The bridge supports bounded model/history/event options plus optional RAG
settings: `rag_paths`, `rag_index_path`, `rag_chunk_size`,
`rag_chunk_overlap`, `rag_top_k`, `rag_context_chars`,
`rag_embedding_model`, `rag_embedding_api_key`, `rag_embedding_base_url`,
`rag_timeout_seconds`, and `rag_citations`. RAG indexes UTF-8 files
incrementally in SQLite and adds bounded local context to the model request.
Provider transcripts, raw Tool input/output, RAG chunks, and secrets are not
stored in history. Citation output is disabled by default.

Installed Tool declarations are discovered from the dedicated
`liteyukibot.agent_sandbox_tools` entry-point group and selected by the
configuration-authoritative `agent-sandbox.tools` list. The model receives a
bounded initial catalog, local catalog search can activate more declarations,
and selected external Tools still use the Broker Tool RPC with the original
authorization context. The resolver package owns static module and Tool
metadata; this package owns the bridge-side catalog and provider loop.

`agent-sandbox` is limited, subscribes to no events, and owns no actions or
controls. It provides built-in file read/write, public HTTPS fetch, and
explicitly allowlisted command primitives. Tool declarations are selected by
configuration and must match the installed static metadata. Each invocation
starts a fresh worker with bounded roots, network policy, wall time, file/output
sizes, and a sanitized environment. This is not a hostile Python-code
containment guarantee for third-party worker tools.

When the Agent bridge is configured and the Commands and Permissions plugins
are enabled, the `liteyukibot.agent.history.clear` capability exposes
`/agent forget`. The command invokes the Broker control owned by the Agent
bridge and clears only the requesting source conversation.

## Development

Run focused tests with:

```bash
uv run pytest packages/agent/tests packages/agent-resolver/tests
uv run python -m scripts.run_agent_install
```

The package publishes only `liteyukibot.bridges` entry points. The former
`liteyukibot.runtimes`, `liteyukibot.plugins`, and Runtime IPC Agent Tool or
control entry points are removed; launching `python -m liteyukibot_agent`
returns `migration_required`.
