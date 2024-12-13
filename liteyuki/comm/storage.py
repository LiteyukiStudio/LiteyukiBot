# -*- coding: utf-8 -*-
"""
共享内存模块。类似于redis，但是更加轻量级并且线程安全
"""
import asyncio
import threading
from typing import Any, Callable, Optional

from liteyuki.comm import channel
from liteyuki.comm.channel import ASYNC_ON_RECEIVE_FUNC, Channel, ON_RECEIVE_FUNC
from liteyuki.utils import IS_MAIN_PROCESS, is_coroutine_callable, run_coroutine_in_thread

if IS_MAIN_PROCESS:
    _locks = {}

_on_main_subscriber_receive_funcs: dict[str, list[ASYNC_ON_RECEIVE_FUNC]] = {}  # type: ignore
"""主进程订阅者接收函数"""
_on_sub_subscriber_receive_funcs: dict[str, list[ASYNC_ON_RECEIVE_FUNC]] = {}  # type: ignore
"""子进程订阅者接收函数"""


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
        self.active_chan = Channel[tuple[str, Optional[dict[str, Any]]]](name="shared_memory-active")
        self.passive_chan = Channel[tuple[str, Optional[dict[str, Any]]]](name="shared_memory-passive")

        self.publish_channel = Channel[tuple[str, Any]](name="shared_memory-publish")

        self.is_main_receive_loop_running = False
        self.is_sub_receive_loop_running = False

    def set(self, key: str, value: Any) -> None:
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
            self.passive_chan.send(
                (
                        "set",
                        {
                                "key"  : key,
                                "value": value
                        }
                )
            )

    def get(self, key: str, default: Optional[Any] = None) -> Optional[Any]:
        """
        获取键值对
        Args:
            key: 键
            default: 默认值

        Returns:
            Any: 值
        """
        if IS_MAIN_PROCESS:
            lock = _get_lock(key)
            with lock:
                return self._store.get(key, default)
        else:
            recv_chan = Channel[Optional[Any]]("recv_chan")
            self.passive_chan.send(
                (
                        "get",
                        {
                                "key"      : key,
                                "default"  : default,
                                "recv_chan": recv_chan
                        }

                )
            )
            return recv_chan.receive()

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
            self.passive_chan.send(
                (
                        "delete",
                        {
                                "key": key
                        }
                )
            )

    def get_all(self) -> dict[str, Any]:
        """
        获取所有键值对
        Returns:
            dict[str, Any]: 键值对
        """
        if IS_MAIN_PROCESS:
            return self._store
        else:
            recv_chan = Channel[dict[str, Any]]("recv_chan")
            self.passive_chan.send(
                (
                        "get_all",
                        {
                                "recv_chan": recv_chan
                        }
                )
            )
            return recv_chan.receive()

    def publish(self, channel_: str, data: Any) -> None:
        """
        发布消息
        Args:
            channel_: 频道
            data: 数据

        Returns:
        """
        self.active_chan.send(
            (
                    "publish",
                    {
                            "channel": channel_,
                            "data"   : data
                    }
            )
        )

    def on_subscriber_receive(self, channel_: str) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]:
        """
        订阅者接收消息时的回调
        Args:
            channel_: 频道

        Returns:
            装饰器
        """
        if not IS_MAIN_PROCESS:
            raise RuntimeError("Cannot subscribe in sub process.")

        def decorator(func: ON_RECEIVE_FUNC) -> ON_RECEIVE_FUNC:
            async def wrapper(data: Any):
                if is_coroutine_callable(func):
                    await func(data)
                else:
                    func(data)

            if IS_MAIN_PROCESS:
                if channel_ not in _on_main_subscriber_receive_funcs:
                    _on_main_subscriber_receive_funcs[channel_] = []
                _on_main_subscriber_receive_funcs[channel_].append(wrapper)
            else:
                if channel_ not in _on_sub_subscriber_receive_funcs:
                    _on_sub_subscriber_receive_funcs[channel_] = []
                _on_sub_subscriber_receive_funcs[channel_].append(wrapper)
            return wrapper

        return decorator

    @staticmethod
    async def run_subscriber_receive_funcs(channel_: str, data: Any):
        """
        运行订阅者接收函数
        Args:
            channel_: 频道
            data: 数据
        """
        [asyncio.create_task(func(data)) for func in _on_main_subscriber_receive_funcs[channel_]]

    async def start_receive_loop(self):
        """
        启动发布订阅接收器循环，在主进程中运行，若有子进程订阅则推送给子进程
        """

        if not IS_MAIN_PROCESS:
            raise RuntimeError("Cannot start receive loop in sub process.")
        while True:
            data = await self.active_chan.async_receive()
            if data[0] == "publish":
                # 运行主进程订阅函数
                await self.run_subscriber_receive_funcs(data[1]["channel"], data[1]["data"])
                # 推送给子进程
                self.publish_channel.send(data)


class GlobalKeyValueStore:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = KeyValueStore()
        return cls._instance


shared_memory: KeyValueStore = GlobalKeyValueStore.get_instance()   # 共享内存对象

# 全局单例访问点
if IS_MAIN_PROCESS:
    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "get")
    def on_get(data: tuple[str, dict[str, Any]]):
        key = data[1]["key"]
        default = data[1]["default"]
        recv_chan = data[1]["recv_chan"]
        recv_chan.send(shared_memory.get(key, default))


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "set")
    def on_set(data: tuple[str, dict[str, Any]]):
        key = data[1]["key"]
        value = data[1]["value"]
        shared_memory.set(key, value)


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "delete")
    def on_delete(data: tuple[str, dict[str, Any]]):
        key = data[1]["key"]
        shared_memory.delete(key)


    @shared_memory.passive_chan.on_receive(lambda d: d[0] == "get_all")
    def on_get_all(data: tuple[str, dict[str, Any]]):
        recv_chan = data[1]["recv_chan"]
        recv_chan.send(shared_memory.get_all())

_ref_count = 0  # import 引用计数, 防止获取空指针
if not IS_MAIN_PROCESS:
    if (shared_memory is None) and _ref_count > 1:
        raise RuntimeError("Shared memory not initialized.")
    _ref_count += 1
