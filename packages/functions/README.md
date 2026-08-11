# LiteyukiBot v7 Functions

`liteyukibot-v7-functions` is the v6 Liteyuki resource-function executor for
LiteyukiBot v7. It registers the `.lyf`, `.lyfunction`, and `.mcfunction`
extensions through the kernel `liteyukibot.function_executors` entry-point
group.

It preserves the v6 resource language: `var`, `api`, `function`, `sleep`,
`nohup`, `await`, `end`, and `cmd`. API and command instructions require a
caller-supplied capability; installing this package never grants resource files
access to adapter APIs or the local operating-system shell.

The old v6 `eval` parsing is intentionally replaced by literal parsing. Values
that are not literals remain strings, matching normal legacy variable lookup.
