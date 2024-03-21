import os

from src.utils.data import LiteModel, Database as DB

DATA_PATH = "data/liteyuki"

user_db = DB(os.path.join(DATA_PATH, 'users.ldb'))
plugin_db = DB(os.path.join(DATA_PATH, 'plugins.ldb'))


class User(LiteModel):
    user_id: str
    username: str = ""
    lang: str = "en"


class InstalledPlugin(LiteModel):
    module_name: str


def auto_migrate():
    user_db.auto_migrate(User)
    plugin_db.auto_migrate(InstalledPlugin)
