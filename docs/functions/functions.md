# Functions and Calls

## Declaration

Both forms are valid:

```lyf
fn no_arguments {
    pass
}

fn greet(name) {
    return {"message": name}
}

async fn load(name) {
    return await profile.inspect(name)
}
```

Parentheses are optional only for a zero-parameter function. Parameters are
comma-separated identifiers. Default parameters, variadic parameters and
Python annotations are not part of Alpha 7.

## Calls

Calls use ordinary parentheses:

```lyf
let result = greet("user")
let profile = await load("user")
```

The command-style forms `echo value` and `print(value)` are syntax sugar for
the explicitly imported core `terminal` Library. No other bare command syntax
exists.

Function calls resolve in this order: local function, same-pack function,
then an explicitly imported Library export. A missing name is a preflight
diagnostic when statically provable and a stable runtime error otherwise.

## Return values

```lyf
return
return value
return first, second, third
```

Multiple return expressions form one ordered tuple. A function without `return`
returns `null`. Tool handlers additionally validate the returned value against
their declared output schema.

## Async rules

`async fn` may await an async Function Library or another async function:

```lyf
async fn work() {
    await async.sleep(1)
    return await other()
}
```

`await` in a synchronous function is a diagnostic. `sync fn` is a reserved
parse-only declaration and never creates a blocking execution path.

## Reserved control flow

The following syntax is parsed to a dedicated unsupported AST node so editors
can highlight it and migration tools can locate it:

```lyf
while condition { ... }
for item in values { ... }
for i := 0; i < 5; i += 1 { ... }
```

Alpha 7 does not execute loops, `terminal.exec`, arbitrary process calls,
`nohup`, `cmd`, `api` or `eval`.
