# LiteyukiBot v7 Commands

`liteyukibot-v7-commands` provides the versioned `liteyukibot.commands@2`
service and a protocol-neutral EventBus command router.

The parser recognizes configurable non-empty prefixes, command names, aliases,
and explicit argument/option schemas. Hierarchical subcommand routing is
supported through canonical command paths.

```toml
[plugins]
enabled = ["liteyukibot.permissions", "liteyukibot.commands"]

[plugins.config."liteyukibot.commands"]
prefixes = ["/"]
```

Consumers register `CommandSpec` and a synchronous or asynchronous handler.
The handler receives `CommandInvocation`, including the normalized command and
unparsed argument text, and returns the kernel's `HandlerResult`.

```python
from liteyukibot_commands import (
    ArgumentSpec,
    CommandSchema,
    CommandSpec,
    OptionSpec,
    integer_value,
)

spec = CommandSpec(
    "echo",
    schema=CommandSchema(
        arguments=(ArgumentSpec("text"),),
        options=(OptionSpec("times", aliases=("n",), converter=integer_value, default=1),),
    ),
)

def echo(invocation):
    parsed = invocation.parse()
    return invocation.reply(str(parsed.arguments["text"]) * int(parsed.options["times"]))
```

Quoting, escaping, `--name value`, `--name=value`, short aliases, flags,
repeatable options, `--`, and conversion failures have platform-independent
semantics. Parsing errors expose stable codes through `CommandParseError`.

## Development

Keep command parsing and routing protocol-neutral. Update parser tests for all
new syntax or error behavior, then run
`uv run pytest packages/commands/tests` and
`uv run python -m scripts.run_commands_install`.
