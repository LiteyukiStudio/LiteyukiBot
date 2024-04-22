import os

from pydantic import Field

from .data import Database, LiteModel, Database

DATA_PATH = "data/liteyuki"

user_db: Database = Database(os.path.join(DATA_PATH, "users.ldb"))
group_db: Database = Database(os.path.join(DATA_PATH, "groups.ldb"))
plugin_db: Database = Database(os.path.join(DATA_PATH, "plugins.ldb"))
common_db: Database = Database(os.path.join(DATA_PATH, "common.ldb"))


class User(LiteModel):
    TABLE_NAME = "user"
    user_id: str = Field(str(), alias="user_id")
    username: str = Field(str(), alias="username")
    profile: dict[str, str] = Field(dict(), alias="profile")
    enabled_plugins: list[str] = Field(list(), alias="enabled_plugins")
    disabled_plugins: list[str] = Field(list(), alias="disabled_plugins")


class Group(LiteModel):
    TABLE_NAME = "group_chat"
    # Group是一个关键字，所以这里用GroupChat
    group_id: str = Field(str(), alias="group_id")
    group_name: str = Field(str(), alias="group_name")
    enabled_plugins: list[str] = Field([], alias="enabled_plugins")
    disabled_plugins: list[str] = Field([], alias="disabled_plugins")
    enable: bool = Field(True, alias="enable")  # 群聊全局机器人是否启用


class InstalledPlugin(LiteModel):
    TABLE_NAME = "installed_plugin"
    module_name: str = Field(str(), alias="module_name")
    version: str = Field(str(), alias="version")


class GlobalPlugin(LiteModel):
    TABLE_NAME = "global_plugin"
    liteyuki: bool = Field(True, alias="liteyuki")  # 是否为LiteYuki插件
    module_name: str = Field(str(), alias="module_name")
    enabled: bool = Field(True, alias="enabled")


class StoredConfig(LiteModel):
    TABLE_NAME = "stored_config"
    config: dict = {}


class TempConfig(LiteModel):
    """储存临时键值对的表"""
    TABLE_NAME = "temp_data"
    data: dict = {}


def auto_migrate():
    user_db.auto_migrate(User())
    group_db.auto_migrate(Group())
    plugin_db.auto_migrate(InstalledPlugin(), GlobalPlugin())
    common_db.auto_migrate(GlobalPlugin(), StoredConfig(), TempConfig())
