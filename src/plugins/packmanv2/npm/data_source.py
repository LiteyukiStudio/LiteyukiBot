import json
from pathlib import Path

import aiofiles
from pydantic import BaseModel

from src.utils.base.config import get_config
from src.utils.io import fetch

NONEBOT_PLUGIN_STORE_URL: str = "https://registry.nonebot.dev/plugins.json"  # NoneBot商店地址
LITEYUKI_PLUGIN_STORE_URL: str = "https://bot.liteyuki.icu/assets/plugins.json"  # 轻雪商店地址


class Session:
    def __init__(self, session_type: str, session_id: int | str):
        self.session_type = session_type
        self.session_id = session_id


async def update_local_store_index() -> list[str]:
    """
    更新本地插件索引库
    Returns:
        新增插件包名列表list[str]
    """
    url = "https://registry.nonebot.dev/plugins.json"
    save_file = Path(get_config("data_path"), "data/liteyuki") / "pacman/plugins.json"
    raw_text = await fetch(url)
    data = json.loads(raw_text)
    with aiofiles.open(save_file, "w") as f:
        await f.write(raw_text)
