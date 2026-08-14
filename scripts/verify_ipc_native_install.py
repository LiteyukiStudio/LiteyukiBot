from liteyukibot_ipc_native import LYIP_NATIVE_ABI, SharedSpscRing, native_available

assert LYIP_NATIVE_ABI == 1
assert native_available

ring = SharedSpscRing("lyip-install-smoke", 1, 16)
assert ring.try_push(b"native")
assert ring.try_pop() == b"native"
