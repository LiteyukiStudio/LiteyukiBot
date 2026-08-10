# LiteyukiBot v7 Commands

`liteyukibot-v7-commands` provides the versioned `liteyukibot.commands@1`
service and a protocol-neutral EventBus command router.

The alpha parser recognizes configurable non-empty prefixes, command names,
and aliases. It deliberately leaves options, subcommands, and typed argument
parsing to command handlers.

```toml
[plugins]
enabled = ["liteyukibot.permissions", "liteyukibot.commands"]

[plugins.config."liteyukibot.commands"]
prefixes = ["/"]
```

Consumers register `CommandSpec` and a synchronous or asynchronous handler.
The handler receives `CommandInvocation`, including the normalized command and
unparsed argument text, and returns the kernel's `HandlerResult`.
