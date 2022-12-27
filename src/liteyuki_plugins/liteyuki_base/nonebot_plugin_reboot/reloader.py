import threading
from multiprocessing import get_context

import nonebot
from nonebot import logger

from .config import plugin_config

_nb_run = nonebot.run


class Reloader:
    event: threading.Event = None

    @classmethod
    def reload(cls, delay: int = 0):
        if cls.event is None:
            raise RuntimeError()
        if delay > 0:
            threading.Timer(delay, function=cls.event.set).start()
            return
        cls.event.set()


def _run(ev: threading.Event, *args, **kwargs):
    Reloader.event = ev
    _nb_run(*args, **kwargs)


def run(*args, **kwargs):
    should_exit = False
    ctx = get_context("spawn")
    while not should_exit:
        event = ctx.Event()
        process = ctx.Process(
            target=_run,
            args=(
                event,
                *args,
            ),
            kwargs=kwargs,
        )
        process.start()
        while not should_exit:
            if event.wait(1):
                logger.info("Receive reboot event")
                process.terminate()
                process.join(plugin_config.reboot_grace_time_limit)
                if process.is_alive():
                    logger.warning(
                        f"Cannot shutdown gracefully in {plugin_config.reboot_grace_time_limit} second, force kill process."
                    )
                    process.kill()
                break
            elif process.is_alive():
                continue
            else:
                # Process stoped without setting event
                should_exit = True


nonebot.run = run
