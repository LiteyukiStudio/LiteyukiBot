# v6 Migration

Alpha 7 is a hard language boundary. The v6 executor is not a compatibility
fallback for the new `.lyf` runtime.

## Rejected forms

The following require `migration_required`:

- `.lyfunction` and `.mcfunction` files;
- v6 `var`, `api`, `cmd`, `nohup`, `await`, `end` and line-oriented `function`
  instructions;
- the Kernel `FUNCTION_DISPATCH_SERVICE` global Dispatcher contract;
- `liteyukibot.function_executors` entries that claim the Alpha 7 `.lyf`
  language;
- unowned workspace functions and resource packs not bound to an enabled
  Native/Cordis extension.

The old package may remain available only as a separately documented v6
compatibility asset while Alpha 7 is developed. It must not be auto-selected
for an Alpha 7 resource pack.

## Rewrite guidance

- Replace module-level bare assignments with `let` or `const`.
- Replace `api` and `cmd` with an explicit Python Function Library or Tool.
- Replace `nohup` with a host-owned Python task and cleanup contract.
- Replace v6 interpolation/evaluation with JSON-safe LYF expressions.
- Replace implicit Agent behavior with `@agent(tool)` or `@agent(prompt)`.
- Replace platform-specific event context with the protocol-neutral EventContext.
