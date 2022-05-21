import aiohttp

from extraApi.base import ExtraData


async def get_reply_data():
    app_key = ExtraData.get_global_data(key="kami.ai.key", default="")
