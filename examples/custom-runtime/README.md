# Custom runtime example

This package is a protocol-v4 child runtime. `RuntimeSupervisor` supplies its
connection environment and owns restart policy. The child keeps one receive
pump and runs Event/Action work in bounded tasks so correlated Action responses
continue to be routed while handlers are awaiting them.

```bash
uv build
```
