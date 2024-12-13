from nonebot import get_plugin_config
from pydantic import BaseModel

NOTICE = "notice"
MESSAGE = "message"

class Config(BaseModel):
    # required fields
    gotify_token: str

    # optional fields
    gotify_url: str = "http://127.0.0.1:40266"
    gotify_priority: int = 5
    gotify_nickname: str = "NoneBot"
    gotify_title: str = "{message_type}: {nickname}({user_id})"
    gotify_message: str = "{message}"
    gotify_includes: list[str, ...] = [NOTICE, MESSAGE]


plugin_config = get_plugin_config(Config)
if plugin_config.gotify_url.endswith("/"):
    plugin_config.gotify_url = plugin_config.gotify_url[:-1]
