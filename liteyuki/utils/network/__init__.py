from aiohttp import ClientSession


async def simple_get(url: str) -> str:
    """
    简单异步get请求
    Args:
        url:

    Returns:

    """
    async with ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()
