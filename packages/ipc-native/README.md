# Liteyuki IPC Native

`liteyukibot-v7-ipc-native` is an optional PyO3 package that provides the
shared-memory primitive used by a future LYIP `shm` backend. It does not route
messages and the kernel does not require it.

`SharedSpscRing(name, capacity, slot_size)` creates a named, fixed-size SPSC
ring. A local supervised child receives `name` through its bootstrap channel
and uses `SharedSpscRing.open(name)`. `try_push(bytes)` returns `False` when
the ring is full; `try_pop()` returns `None` when empty. A payload larger than
`slot_size` is rejected without modifying the ring.

The ring uses per-slot atomic sequence numbers with Release publication and
Acquire consumption. One producer and one consumer own the respective
operations. The object is a narrow transport primitive only: retry policy,
backpressure, routing, blob leases, cleanup policy, and all LYIP models stay in
the Python kernel.

Create independent named rings for business and control lanes. Their fixed
capacities are isolated: a full business ring cannot occupy control records.

`native_available` is true only when ABI 1 imports and the extension can create
a real shared-memory SPSC ring on the current platform. Callers must select ZMQ
when it is false.
