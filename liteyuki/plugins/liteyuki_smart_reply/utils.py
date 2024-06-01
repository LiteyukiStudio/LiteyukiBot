from jieba import lcut
from nonebot.utils import run_sync


@run_sync
def get_keywords(text: str) -> list[str, ...]:
    """
    获取关键词
    Args:
        text: 文本
    Returns:
    """
    return lcut(text)
