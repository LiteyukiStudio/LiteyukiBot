import threading

from liteyuki.comm.channel import active_channel


def reload(delay: float = 0.0, receiver: str = "nonebot"):
    """
    重载LiteyukiBot(nonebot)
    Args:
        receiver: 指定重载的进程
        delay:

    Returns:

    """

    if delay > 0:
        threading.Timer(delay, active_channel.send, args=(1,)).start()
        return
    else:
        active_channel.send(1)
