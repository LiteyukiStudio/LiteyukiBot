import aiofiles
from pathlib import Path


async def write_file(
        file_path: str | Path,
        content: str | bytes,
        mode: str = "w",
        **kws,
):
    """
    写入文件
    Args:
        mode: 写入模式
        file_path: 文件路径
        content: 内容
    """
    async with aiofiles.open(file_path, mode, **kws) as f:
        await f.write(content)


async def read_file(
        file_path: str | Path,
        mode: str = "r",
        **kws,
) -> str:
    """
    读取文件
    Args:
        file_path: 文件路径
        mode: 读取模式
    Returns:
    """
    async with aiofiles.open(file_path, mode, **kws) as f:
        return await f.read()
