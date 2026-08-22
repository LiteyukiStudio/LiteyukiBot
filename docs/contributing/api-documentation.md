# API documentation contract

LiteyukiBot documents callable contracts next to their implementation so that
developers, generated API references, and code-reading agents see the same
information. This policy applies to production Python sources under `src/`,
`packages/*/src/`, `packages/ipc-native/python/`, and the qualification
benchmark.

Public TypeScript functions, hooks, React components, and service methods under
`webui/src/` use JSDoc with a purpose summary, `@param` entries, `@returns`, and
`@remarks` for non-obvious behavior or trust boundaries. Local render helpers
remain implementation details and are documented only when their mechanism is
not clear from their types and body.

## Function docstrings

Every class, function, method, property getter, validator, callback, and nested
helper has a docstring. Classes state their ownership or data contract. Public
callables use this shape:

```python
def resolve(name: str, *, required: bool = True) -> Service | None:
    """Resolve a service by its stable registration name.

    Args:
        name: Stable service name to resolve.
        required: Whether absence raises instead of returning `None`.

    Returns:
        The registered service, or `None` when it is optional and absent.

    Raises:
        ServiceNotFoundError: If the service is required but not registered.

    Notes:
        Resolution is read-only and does not instantiate providers.
    """
```

The first line states purpose. `Args` documents every parameter other than
`self` and `cls`. `Returns` is always present, including `None`-returning
commands. `Raises` lists deliberate contract failures. `Notes` is optional for
public callables and records non-obvious logic, ordering, ownership, or
performance behavior.

Private helpers use the same `Args` and `Returns` sections plus `Notes` that
identify them as implementation details and summarize their mechanism. Their
documentation must not imply that they are stable extension APIs.

## Security notes

Callables that intentionally retain a dangerous capability use a `Security`
section. It states:

1. what untrusted or sensitive input crosses the boundary;
2. which checks bound the risk;
3. why the capability remains necessary.

Long explanations belong in
[`docs/security/trusted-boundaries.md`](../security/trusted-boundaries.md), with
the docstring linking to the relevant heading. Do not disclose credentials,
real tokens, exploit payloads, or private deployment details in either place.

## Validation

Run:

```bash
uv run python scripts/check_api_docs.py
```

The checker parses source with the standard-library AST. It requires a
docstring, complete parameter coverage, a `Returns` section, and an internal
`Notes` section. It deliberately does not score prose quality; review remains
responsible for detecting tautological, stale, or misleading descriptions.
TypeScript JSDoc remains covered by the frontend type/build checks and review;
the Python checker does not parse TypeScript syntax.
