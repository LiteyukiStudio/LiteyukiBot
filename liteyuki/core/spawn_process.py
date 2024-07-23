import threading
from multiprocessing import get_context, Event

import nonebot
from nonebot import logger

from liteyuki.plugin.load import load_plugins

timeout_limit: int = 20
__all__ = [
        "ProcessingManager",
        "nb_run",
]


class ProcessingManager:
    event: Event = None

    @classmethod
    def restart(cls, delay: int = 0):
        """
        发送终止信号
        Args:
            delay: 延迟时间，默认为0，单位秒
        Returns:
        """
        if cls.event is None:
            raise RuntimeError("ProcessingManager has not been initialized.")
        if delay > 0:
            threading.Timer(delay, function=cls.event.set).start()
            return
        cls.event.set()


def nb_run(event, *args, **kwargs):
    ProcessingManager.event = event
    nonebot.run(*args, **kwargs)
