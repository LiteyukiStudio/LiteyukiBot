import os

from src.utils.data import LiteModel, SqliteORMDatabase as DB

DATA_PATH = "data/liteyuki"

user_db = DB(os.path.join(DATA_PATH, 'users.ldb'))


class UserModel(LiteModel):
    id: str
    username: str
    lang: str


user_db.auto_migrate(UserModel)
