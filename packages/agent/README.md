# LiteyukiBot Native Agent

The native agent is an agent-only LiteyukiBot v7 runtime. It receives normalized
events from source runtimes and emits ordinary actions back to those sources.
It uses the official OpenAI Python SDK with an OpenAI-compatible endpoint.

For each delivered Event, the kernel sends only the tool schemas authorized for
that event principal. The agent runtime has no executable tool implementation;
every tool request returns through the kernel broker, which checks the same
capabilities again before invoking a package-provided handler.
