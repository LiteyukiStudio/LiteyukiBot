import os

from src.utils.data import LiteModel, Database as DB

DATA_PATH = "data/liteyuki"

user_db = DB(os.path.join(DATA_PATH, 'users.ldb'))


class User(LiteModel):
    user_id: str
    username: str = ""
    lang: str = "en"


user_db.auto_migrate(User)
