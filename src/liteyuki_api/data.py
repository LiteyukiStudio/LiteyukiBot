from typing import Any, Union
import nonebot
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent
from .config import config_data
import pymongo

LiteyukiDB = pymongo.MongoClient(config_data["mongodb"])["liteyuki"]
nonebot.logger.info("已连接到数据库：%s" % config_data["mongodb"])


class Data:
    users = "users"
    groups = "groups"
    globals = "globals"

    def __init__(self, database_name, _id=0):
        """
        可以仅传入event

        :param database_name: 数据库名
        :param _id:
        """
        self.database_name = database_name
        self._id = _id

        self.collection = LiteyukiDB[self.database_name]

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
        self.collection.update_one({"_id": self._id}, {"$set": {key: value}}, upsert=True)

    def del_data(self, key):
        key = key.replace(".", "_")
        self.collection.update_one({"_id": self._id}, {"$unset": {key: 1}})

    def delete(self):
        """
        慎用 删除集合中的文档

        :return:
        """
        self.collection.delete_one({"id": self._id})

    def __str__(self):
        return "Database: %s-%s" % (self.database_name, self._id)

    @staticmethod
    def get_type_id(event: Union[GroupMessageEvent, PrivateMessageEvent]):
        if event.message_type == "group":
            return Data.groups, event.group_id
        elif event.message_type == "private":
            return Data.users, event.user_id
        else:
            return Data.globals, 0
