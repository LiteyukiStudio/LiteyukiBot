# -*- coding: utf-8 -*-
"""
共享内存模块。类似于redis，但是更加轻量级并且线程安全
"""

import threading
from typing import Any, Optional

from liteyuki.utils import IS_MAIN_PROCESS
from liteyuki.comm.channel import Channel

if IS_MAIN_PROCESS:
    _locks = {}


def _get_lock(key):
    if IS_MAIN_PROCESS:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]
    else:
        raise RuntimeError("Cannot get lock in sub process.")


class KeyValueStore:
    def __init__(self):
        self._store = {}

        self.active_chan = Channel(_id="shared_memory-active")
        self.passive_chan = Channel(_id="shared_memory-passive")

    def set(self, key: str, value: any) -> None:
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                self._store[key] = value
        else:
            # 向主进程发送请求拿取
            self.passive_chan.send(("set", key, value))

    def get(self, key: str, default: Optional[any] = None) -> any:
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                return self._store.get(key, default)
        else:
            self.passive_chan.send(("get", key, default))
            return self.active_chan.receive()

    def delete(self, key: str) -> None:
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                if key in self._store:
                    del self._store[key]
                    del _locks[key]
        else:
            # 向主进程发送请求删除
            self.passive_chan.send(("delete", key))

    def get_all(self) -> dict[str, any]:
        if IS_MAIN_PROCESS:
            return self._store
        else:
            self.passive_chan.send(("get_all",))
            return self.active_chan.receive()


class GlobalKeyValueStore:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if IS_MAIN_PROCESS:
            if cls._instance is None:
                with cls._lock:
                    if cls._instance is None:
                        cls._instance = KeyValueStore()
            return cls._instance
        else:
            raise RuntimeError("Cannot get instance in sub process.")


shared_memory: Optional[KeyValueStore] = None

# 全局单例访问点
if IS_MAIN_PROCESS:
    shared_memory = GlobalKeyValueStore.get_instance()


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "get")
    def on_get(d):
        print(shared_memory.get_all())
        shared_memory.active_chan.send(shared_memory.get(d[1], d[2]))
        print("发送数据：", shared_memory.get(d[1], d[2]))


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "set")
    def on_set(d):
        shared_memory.set(d[1], d[2])


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "delete")
    def on_delete(d):
        shared_memory.delete(d[1])
else:
    shared_memory = None

_ref_count = 0  # 引用计数
if not IS_MAIN_PROCESS:
    if (shared_memory is None) and _ref_count > 1:
        raise RuntimeError("Shared memory not initialized.")
    _ref_count += 1
