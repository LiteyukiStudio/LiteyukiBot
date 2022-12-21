from typing import Any

import nonebot

from .config import config_data
import pymongo

LiteyukiDB = pymongo.MongoClient(config_data["mongodb"])["liteyuki"]
nonebot.logger.info("已连接到数据库：%s" % config_data["mongodb"])


class Data:
    users = "users"
    groups = "groups"
    globals = "globals"

    def __init__(self, database_name, _id):
        self.database_name = database_name
        self._id = _id

    def get_data(self, key, default=None) -> Any:
        key = key.replace(".", "_")
        if self.database_name not in LiteyukiDB.list_collection_names():
            return default
        else:
            document = LiteyukiDB[self.database_name].find_one({"_id": self._id})
            if document is None:
                return default
            else:
                return document.get(key, default)

    def set_data(self, key, value):
        key = key.replace(".", "_")
        LiteyukiDB[self.database_name].update_one({"_id": self._id}, {"$set": {key: value}}, upsert=True)
