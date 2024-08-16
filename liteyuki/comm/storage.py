# -*- coding: utf-8 -*-
"""
共享内存模块。类似于redis，但是更加轻量级并且线程安全
"""

import threading
from typing import Optional

from liteyuki.comm.channel import Channel
from liteyuki.utils import IS_MAIN_PROCESS

if IS_MAIN_PROCESS:
    _locks = {}


def _get_lock(key) -> threading.Lock:
    """
    获取锁
    """
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
        """
        设置键值对
        Args:
            key: 键
            value: 值

        """
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                self._store[key] = value
        else:
            # 向主进程发送请求拿取
            self.passive_chan.send(("set", key, value))

    def get(self, key: str, default: Optional[any] = None) -> any:
        """
        获取键值对
        Args:
            key: 键
            default: 默认值

        Returns:
            any: 值
        """
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                return self._store.get(key, default)
        else:
            self.passive_chan.send(("get", key, default))
            return self.active_chan.receive()

    def delete(self, key: str, ignore_key_error: bool = True) -> None:
        """
        删除键值对
        Args:
            key: 键
            ignore_key_error: 是否忽略键不存在的错误

        Returns:
        """
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                if key in self._store:
                    try:
                        del self._store[key]
                        del _locks[key]
                    except KeyError as e:
                        if not ignore_key_error:
                            raise e
        else:
            # 向主进程发送请求删除
            self.passive_chan.send(("delete", key))

    def get_all(self) -> dict[str, any]:
        """
        获取所有键值对
        Returns:
            dict[str, any]: 键值对
        """
        if IS_MAIN_PROCESS:
            return self._store
        else:
            self.passive_chan.send(("get_all",))
            return self.active_chan.receive()


class KeyValueStoreNoLock:
    def __init__(self):
        self._store = {}

        self.active_chan = Channel(_id="shared_memory-active")
        self.passive_chan = Channel(_id="shared_memory-passive")

    def set(self, key: str, value: any) -> None:
        """
        设置键值对
        Args:
            key: 键
            value: 值

        """
        if IS_MAIN_PROCESS:
            self._store[key] = value
        else:
            # 向主进程发送请求拿取
            self.passive_chan.send(("set", key, value))

    def get(self, key: str, default: Optional[any] = None) -> any:
        """
        获取键值对
        Args:
            key: 键
            default: 默认值

        Returns:
            any: 值
        """
        if IS_MAIN_PROCESS:
            return self._store.get(key, default)
        else:
            temp_chan = Channel("temp_chan")
            self.passive_chan.send(("get", key, default, temp_chan))
            return temp_chan.receive()

    def delete(self, key: str, ignore_key_error: bool = True) -> None:
        """
        删除键值对
        Args:
            key: 键
            ignore_key_error: 是否忽略键不存在的错误

        Returns:
        """
        if IS_MAIN_PROCESS:
            if key in self._store:
                try:
                    del self._store[key]
                    del _locks[key]
                except KeyError as e:
                    if not ignore_key_error:
                        raise e
        else:
            # 向主进程发送请求删除
            self.passive_chan.send(("delete", key))

    def get_all(self) -> dict[str, any]:
        """
        获取所有键值对
        Returns:
            dict[str, any]: 键值对
        """
        if IS_MAIN_PROCESS:
            return self._store
        else:
            temp_chan = Channel("temp_chan")
            self.passive_chan.send(("get_all", temp_chan))
            return temp_chan.receive()


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
    def on_get(data: tuple[str, str, any, Channel]):
        data[3].send(shared_memory.get(data[1], data[2]))


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "set")
    def on_set(data: tuple[str, str, any]):
        shared_memory.set(data[1], data[2])


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "delete")
    def on_delete(data: tuple[str, str]):
        shared_memory.delete(data[1])


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "get_all")
    def on_get_all(data: tuple[str, Channel]):
        if data[0] == "get_all":
            data[1].send(shared_memory.get_all())
else:
    # 子进程在入口函数中对shared_memory进行初始化
    shared_memory = None

_ref_count = 0  # import 引用计数, 防止获取空指针
if not IS_MAIN_PROCESS:
    if (shared_memory is None) and _ref_count > 1:
        raise RuntimeError("Shared memory not initialized.")
    _ref_count += 1
