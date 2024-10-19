import asyncio
from asyncio import Future
from collections.abc import Coroutine
from typing import Any

import aiohttp
from magicoca import Chan
from nonebot import logger
from pydantic import BaseModel

from .config import plugin_config

msg_chan = Chan["Message"]()


class Message(BaseModel):
    title: str
    message: str
    priority: int = plugin_config.gotify_priority


def fetch_msg() -> Future[Any]:
    return asyncio.get_event_loop().run_in_executor(func=msg_chan.recv, executor=None)
