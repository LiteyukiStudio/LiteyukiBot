# LiteyukiBot Native Agent

The native agent is an agent-only LiteyukiBot v7 runtime. It receives normalized
events from source runtimes and emits ordinary actions back to those sources.
It uses the official OpenAI Python SDK with an OpenAI-compatible endpoint.

For each delivered Event, the kernel sends only the tool schemas authorized for
that event principal. The agent runtime has no executable tool implementation;
every tool request returns through the kernel broker, which checks the same
capabilities again before invoking a package-provided handler.

The `agent` runtime options bound each delivered event: `history_limit` defaults
to 40 messages and is also the maximum retained SQLite history per source
runtime, bot, and conversation. Retention is applied on every write; changing
the limit only affects subsequent writes. `max_concurrent_events` defaults to 16, `max_tool_rounds` to 4,
`model_timeout_seconds` to 60, and `event_timeout_seconds` to 120. A model or
event timeout produces a failed terminal delivery without recording model input,
tool arguments, or response content in logs.

When the Commands and Permissions plugins are enabled, operators may grant
`liteyukibot.agent.history.clear` to expose `/agent forget`. The command is
handled by the kernel, sends one protocol-v5 control request to the native
Agent child, and clears only the requesting source runtime, bot, and
conversation. It never sends a model request and the permission audit contains
no conversation content.

## Development

Keep model-provider state and agent execution in this runtime package. Tool
authorization and invocation remain kernel-brokered. Run
`uv run pytest packages/agent/tests` and
`uv run python -m scripts.run_agent_install` after changes.
