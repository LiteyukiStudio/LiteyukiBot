# Core Event And Action v1

The kernel owns immutable, JSON-safe protocol-neutral values. SDK objects,
transport clients and credentials do not enter these models.

## Event

`EventEnvelope` carries a stable ID, `runtime_id`, adapter name, bot identity,
private or group conversation, optional actor, optional message and a reply
token. An adapter account configuration key is its `runtime_id`; the protocol
account identifier is `bot_id`.

Messages support exactly four segment types:

- `text` with `data.text`
- `mention` with `data.user_id` or `data.scope = "all"`
- `reply` with `data.message_id`
- `image` with `data.url`

## Action

Alpha15 supports only `SendMessage`. It requires either an explicit
conversation or an adapter-issued reply token. Adapter execution must reject
proactive actions and actions whose event, runtime or bot identity differs from
the source event.

The bounded `EventBus` preserves FIFO processing for each runtime, bot and
conversation key. Capacity, enqueue timeout, handler timeout and concurrency
come from `[core]` configuration.

Handlers may report structured failures and action results in `HandlerResult`.
`EventBus` includes those reports in `DispatchResult`; hosts must inspect the
returned status and failures instead of treating every completed coroutine as a
successful handler execution.

Evidence: `packages/kernel/src/liteyukibot_kernel/events/` and the kernel and
OneBot package tests.
