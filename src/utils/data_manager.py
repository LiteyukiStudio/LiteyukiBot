import os

from src.utils.data import LiteModel, Database as DB

DATA_PATH = "data/liteyuki"

user_db = DB(os.path.join(DATA_PATH, 'users.ldb'))
group_db = DB(os.path.join(DATA_PATH, 'groups.ldb'))
plugin_db = DB(os.path.join(DATA_PATH, 'plugins.ldb'))


class User(LiteModel):
    user_id: str
    username: str = ""
    lang: str = "en"
    enabled_plugins: list[str] = []
    disabled_plugins: list[str] = []


class GroupChat(LiteModel):
    # Group是一个关键字，所以这里用GroupChat
    group_id: str
    group_name: str = ""
    enabled_plugins: list[str] = []
    disabled_plugins: list[str] = []


class InstalledPlugin(LiteModel):
    module_name: str


def auto_migrate():
    user_db.auto_migrate(User)
    group_db.auto_migrate(GroupChat)
    plugin_db.auto_migrate(InstalledPlugin)
