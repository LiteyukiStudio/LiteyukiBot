# Bindings and Values

## Binding declarations

```lyf
let mutable_value = 1
val another_mutable_value = 2
const fixed_value = "fixed"
```

`let` is canonical. `val` is an exact syntax alias for `let`; it does not mean
immutable. `const` cannot be assigned again in the same lexical scope.

The grammar is:

```text
binding = ( "let" | "val" | "const" ), identifier, "=", expression ;
```

Bindings are lexical. A function parameter is an initially mutable local
binding. An inner function may read an outer binding but cannot mutate an outer
`const`.

## Assignment

An assignment updates an existing local binding:

```lyf
let count = 0
count = 1
```

This is invalid:

```lyf
count = 1        # no prior local declaration
const answer = 1
answer = 2       # const reassignment
```

Module-level implicit declarations are not supported. Unused declarations may
produce a diagnostic, but the parser does not reinterpret them as comments and
the evaluator does not rely on Python garbage-collector behavior.

Compound assignments such as `+=` are reserved for the future loop subset and
are parse-only in Alpha 7.

## Destructuring

Tuple and list values can be destructured positionally:

```lyf
let (first, second, ignored) = make_values()
let (x, y, z) = (1, 2, 3)
```

`_` discards one value. The number of non-discarded positions must match the
source tuple/list length. Object/map destructuring is not supported.

The exact declaration form for a destructuring binding is:

```text
binding-target = identifier | "_" | "(", binding-target-list, ")" ;
```

## Expressions

Alpha 7 executes literals, names, tuple/list/object construction, function
calls, Library calls and `await` calls. Expression results must remain JSON-safe
when crossing a Tool, Event or Broker boundary.

The parser also recognizes arithmetic, comparisons, boolean expressions,
indexing and reserved loop expressions so it can provide location-aware
unsupported diagnostics. No unsupported expression is silently evaluated by a
fallback Python operation.
