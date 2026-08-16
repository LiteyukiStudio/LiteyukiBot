# Custom runtime example

This package is a historical protocol-v5 child runtime. `RuntimeSupervisor`
supplies its connection environment and owns restart policy. The child keeps
one receive pump and runs Event/Action work in bounded tasks so correlated
Action responses continue to be routed while handlers are awaiting them.

It is not a standalone B5 broker peer. No installable broker-peer integration
example exists yet; see `docs/specs/runtime-ipc-v6.md` for the implemented
broker foundation.

```bash
uv build
```
