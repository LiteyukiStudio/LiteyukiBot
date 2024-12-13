async def fetch(url: str) -> str:
    """
    异步get请求
    Args:
        url:

    Returns:

    """
    async with ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.text()
