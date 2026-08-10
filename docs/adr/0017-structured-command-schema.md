# ADR 0017: Use Explicit Structured Command Schemas

- Status: Accepted
- Date: 2026-08-10

## Context

ADR 0014 introduced deterministic root-command routing but intentionally left
all arguments as one raw string. Native plugins now need reusable quoting,
options, conversion, and help metadata. Letting each handler choose shell
parsers or infer behavior from Python annotations would produce incompatible
grammars and hidden dependency-injection rules.

The command layer must remain protocol-neutral and dependency-light. Chat input
is not a platform shell, and parser behavior must be identical on Linux,
Windows, and macOS.

## Decision

`liteyukibot.commands@1` adds an explicit `CommandSchema` composed of frozen
`ArgumentSpec` and `OptionSpec` values. `CommandSpec` carries the schema and
`CommandInvocation.parse()` parses its preserved `raw_arguments`. Commands
without a schema continue to receive the same raw text and are not parsed
automatically; explicitly parsing unmodeled input reports an unexpected
argument.

The tokenizer has one platform-independent chat grammar:

- Unicode whitespace separates tokens;
- single and double quotes preserve whitespace and permit empty tokens;
- backslash escapes exactly the next character;
- unterminated quotes and trailing escapes are errors.

Options support `--name value`, `--name=value`, one-character short aliases,
boolean flags, repeatable values, repeatable flag counts, required options, and
the `--` terminator. Short-option aggregation is not supported. Positionals
support required, optional, and final variadic arguments.

Conversion is explicit. A spec stores a callable from string to object; the
package provides string, base-10 integer, float, and strict `true`/`false`
converters. Handler annotations are never inspected. Conversion failures retain
their exception chain for diagnostics and expose only a stable
`CommandParseError` code, subject, and token to consumers.

`ParsedCommand` freezes the top-level argument and option mappings. Repeated
values are tuples. A custom converter owns the mutability and semantics of the
object it returns; the command package does not recursively rewrite arbitrary
third-party values.

Schema validation rejects ambiguous definitions before registration: invalid
names, duplicate argument or option names, duplicate short aliases, required
arguments after optional arguments, and non-final variadic arguments.

This decision does not yet make router-side parsing mandatory or define
localized usage-error replies. Handlers opt in through `invocation.parse()`.
Hierarchical routing and automatic parse-error handling are separate follow-up
changes so this parser can be tested independently.

## Consequences

Plugins share one deterministic grammar without adding Click, Typer, shell
semantics, or annotation-driven magic. Schemas can later drive detailed help
without importing handler internals.

Custom converters must be synchronous and should be side-effect free. Network
or database lookup belongs in the async handler after structural parsing.
Subcommands, parent-path aliases, localized error rendering, and mention
activation remain outside this record.
