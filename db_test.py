from liteyuki.internal.base.data import *


class People(LiteModel):
    TABLE_NAME: str = "people"
    name: str = ""
    age: int = 0
    sex: str = ""
    identity: str = ""


db = Database("data/test/test.ldb")

db.where()

