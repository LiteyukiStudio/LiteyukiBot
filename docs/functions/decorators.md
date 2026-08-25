# Decorators

Decorators are declarations, not arbitrary runtime calls. They are validated
during preflight and cannot be created dynamically by a function.

## Agent Tool

```lyf
@agent(
    tool,
    name="say_hello",
    description="Return a greeting",
    input={
        "type": "object",
        "properties": {"name": {"type": "string"}},
        "required": ["name"],
        "additionalProperties": false
    },
    output={
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
        "additionalProperties": false
    },
    capabilities=["liteyukibot.agent.tool"]
)
fn say_hello(name) {
    return {"message": "hello {name}"}
}
```

Required attributes are `name`, `description`, `input` and `output`. Schemas
must be Draft 2020-12 object schemas. `capabilities` is optional and is checked
by the parent Native/Cordis host before invocation.

The full Tool ID is `<extension_id>.lyf.<name>`. Local names must be unique in
the owning resource pack, and the full ID must not collide with a Python Tool
or another resource pack. The function signature must accept the declared
input property names; the host validates both input and output.

Agent Tool invocation receives an immutable authorization context. A function
cannot replace the event ID, runtime ID, bot ID or actor ID supplied by the
host.

## Agent prompt preset

```lyf
@agent(prompt, name="friendly_reply", description="Friendly Chinese reply")
fn friendly_reply() {
    return {
        "prompt": "Reply in friendly Chinese.",
        "examples": [
            {"when": "hello", "answer": "你好喵!"}
        ]
    }
}
```

Prompt functions must be deterministic and preflightable. They may use JSON
literals, constant bindings and pure Library exports only. Event values,
mutable state, network calls, Tool calls and `async` operations are forbidden
in a prompt preset.

The full preset ID is `<extension_id>.lyf.prompt.<name>`. The host validates the
named result, applies bounded prompt/example sizes, and places it in the
verified Agent prompt catalog. A user-supplied prompt string is never accepted
as a substitute for a registered preset.

## Event handler

```lyf
@events(
    "message.created",
    where={"conversation.type": "private"}
)
async fn on_message(event) {
    terminal.echo(event.message.plain_text)
}
```

The first argument is a validated protocol topic. `where` is an optional map of
exact filters over the public EventContext projection. Host-specific `target`,
Cordis `ctx`, platform SDK values and delivery `ttl` are not Alpha 7 syntax.

An event function may have zero parameters or one `event` parameter. The host
owns the EventBus subscription, per-event timeout, task ownership and cleanup.

## Parse-only decorator forms

Unknown decorators, malformed options and reserved forms are diagnosed during
preflight. They must never be treated as ordinary function calls. Future
decorators can be added only with a versioned specification and a host-owned
lifecycle contract.
