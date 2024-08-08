import threading

from nonebot import logger
from liteyuki.core.spawn_process import chan_in_spawn_nb


def reload(delay: float = 0.0, receiver: str = "nonebot"):
    """
    重载LiteyukiBot(nonebot)
    Args:
        receiver: 指定重载的进程
        delay:

    Returns:

    """

    chan_in_spawn_nb.send(1, receiver)
    logger.info(f"Reloading LiteyukiBot({receiver})...")
