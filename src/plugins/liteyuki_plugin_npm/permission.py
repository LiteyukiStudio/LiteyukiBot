# 插件权限管理器，对api调用进行hook限制，防止插件滥用api
from src.utils.data import LiteModel


class PermissionAllow(LiteModel):
    plugin_name: str
    api_name: str
    allow: bool