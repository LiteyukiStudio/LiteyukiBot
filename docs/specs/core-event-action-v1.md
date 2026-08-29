# Core Event And Action v1

The kernel owns immutable, JSON-safe protocol-neutral values. SDK objects,
transport clients and credentials do not enter these models.

## Event

`EventEnvelope` carries a stable ID, `runtime_id`, adapter name, bot identity,
optional private or group conversation, optional actor, optional message, a
reply token, adapter-normalized JSON-safe `details`, and the original JSON-safe
`raw` payload. An adapter account configuration key is its `runtime_id`; the
protocol account identifier is `bot_id`. Events without a conversation use an
account-level ordering key.

Portable messages support:

- `text` with `data.text`
- `mention` with `data.user_id` or `data.scope = "all"`
- `reply` with `data.message_id`
- `image`, `audio`, `video` and `file` with a non-empty `data.url` or `data.file_id`
- `emoji` with `data.id`
- `adapter` with `data.adapter`, native `data.type` and JSON-safe `data.data`

The adapter segment is an explicit escape hatch. A backend must reject an
adapter segment targeted at another adapter rather than guessing a conversion.

## Action

`SendMessage` requires either an explicit conversation or an adapter-issued
reply token. `DeleteMessage` recalls one message by adapter-issued message ID.
`RespondRequest` approves or rejects the request represented by its source
event. `AdapterAction` calls an explicitly named extension on the source
adapter with JSON-safe parameters; portable operations must not be tunneled
through that escape hatch.

Adapter execution rejects proactive actions and actions whose event, runtime,
bot or explicit adapter identity differs from the source event.

The bounded `EventBus` preserves FIFO processing for each runtime, bot and
conversation key. Capacity, serialized event byte budget, enqueue timeout,
handler timeout, action timeout, shutdown timeout and concurrency come from
`[core]` configuration. Events over the byte budget are rejected before
admission. Event
handlers, action executors, action backends and authorization policies are
async-only callbacks; registration rejects synchronous callables so deadlines
cannot be bypassed by blocking the event loop.
When cancellation cannot stop a handler or action, the EventBus keeps that
operation as a barrier for its ordering key and exposes it through background
task status before admitting later work for the same key.
Actions emitted while dispatching one event are attempted in order. If an
earlier action remains running after its timeout, later actions are reported as
`ACTION_BLOCKED` and are not started until the barrier is gone.

Handlers may report structured failures and action results in `HandlerResult`.
`EventBus` includes those reports in `DispatchResult`; hosts must inspect the
returned status and failures instead of treating every completed coroutine as a
successful handler execution.

Evidence: `packages/kernel/src/liteyukibot_kernel/events/` and the kernel and
OneBot package tests.
