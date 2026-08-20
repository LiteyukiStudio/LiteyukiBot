# Lexical Structure

## File header

The first non-comment declaration must be:

```lyf
@version 1.0
```

Only one version declaration is allowed. Unsupported versions fail preflight;
the host must not guess a compatible grammar.

## Comments and whitespace

Spaces, tabs and newlines separate tokens. The following comments are valid:

```lyf
# line comment
// line comment
/*
   block comment
*/
```

`///` is a documentation comment. It is preserved in the AST and attaches to
the next function or decorated declaration. A documentation comment does not
change execution.

Comment markers inside a string are ordinary string contents. An unterminated
block comment is a parse error.

## Identifiers

Identifiers use ASCII letters, digits and `_`, and cannot start with a digit:

```text
identifier = letter | "_", { letter | digit | "_" } ;
```

Keywords are reserved and cannot be used as identifiers:

```text
@version  use  let  val  const  fn  async  return  await  pass
while  for  in  terminal  sync  true  false  null
```

Function, Library and Tool names are case-sensitive.

## Literals

LYF values are JSON-safe:

```lyf
null
true
false
42
3.14
"text"
[1, 2, 3]
{"name": "value"}
(1, 2, 3)
```

Object entries use `key: value`. The set-like form
`{"key", "value"}` is invalid. Object keys must be strings or identifiers
that normalize to strings.

Numbers must be finite. Bytes, Python objects, sets, tuples returned directly
to a Broker Tool, and arbitrary class instances are not LYF values.

## String interpolation

Double-quoted strings may contain simple binding interpolation:

```lyf
let name = "Liteyuki"
terminal.echo("hello {name}")
```

An interpolation contains one identifier only. Calls, indexing, operators and
Library access inside `{...}` are invalid; evaluate those expressions first and
bind the result.

## Source locations

The parser records byte offset, line and one-based column for every declaration,
expression and diagnostic. Hosts identify a source as
`<resource-pack>:<relative-function-path>` and never expose local absolute
paths in a user-facing error.
