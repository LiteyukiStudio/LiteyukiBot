import json
import os
from typing import Any, Union, Tuple, Dict

import nonebot
import pymongo
from nonebot.adapters.onebot.v11.event import GroupMessageEvent, PrivateMessageEvent
from nonebot.utils import run_sync

from .config import config_data, Path

LiteyukiDB = pymongo.MongoClient(config_data["mongodb"])["liteyuki"]
try:
    nonebot.logger.info(f'Connecting to MongoDB: {config_data["mongodb"]}')
    LiteyukiDB["globals"].update_one({"_id": "write_test"}, {"$set": {"key": "value"}}, upsert=True)
    nonebot.logger.success(f'Connected to MongoDB successfully: {config_data["mongodb"]}')
    mongo = True
except:
    nonebot.logger.error(f'Can not connect to MongoDB: {config_data["mongodb"]}')
    nonebot.logger.error("Liteyuki has not connect to MongoDB, change to json, this map affect performance")
    mongo = False
    if not os.path.exists(os.path.join(Path.data, "database")):
        os.makedirs(os.path.join(Path.data, "database"))


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
        if mongo:
            self.collection = LiteyukiDB[self.database_name]
        else:
            self.collection = os.path.join(Path.data, f"database/{self.database_name}.json")

    async def get(self, key, default=None) -> Any:
        key = key.replace(".", "_")
        if mongo:
            document = await run_sync(self.collection.find_one)({"_id": self._id})
        else:
            document = None
            if os.path.exists(self.collection):
                json_data = await run_sync(json.load)(open(self.collection, encoding="utf-8"))
                for document in json_data:
                    if ("_id", self._id) in document.items():
                        break
        if document is None:
            return default
        else:
            return document.get(key, default)

    async def get_many(self, key_data=Dict[str, Any]) -> Tuple:
        """
        :param key_data: {key1: default1, key2: default2}
        :return:
        """
        if mongo:
            document = await run_sync(self.collection.find_one)({"_id": self._id})
        else:
            document = None
            if os.path.exists(self.collection):
                json_data = await run_sync(json.load)(open(self.collection, encoding="utf-8"))
                document = None
                for document in json_data:
                    if ("_id", self._id) in document.items():
                        break
        value = []
        for key, default in key_data.items():
            if document is None:
                value.append(default)
            else:
                value.append(document.get(key, default))
        return tuple(value)

    async def set(self, key, value):
        key = key.replace(".", "_")
        if mongo:
            await run_sync(self.collection.update_one)({"_id": self._id}, {"$set": {key: value}}, upsert=True)
        else:
            if not os.path.exists(self.collection):
                json_file = await run_sync(open)(self.collection, "w", encoding="utf-8")
                await run_sync(json_file.write)("[]")
                await run_sync(json_file.close)()
            json_data = await run_sync(json.load)(open(self.collection, encoding="utf-8"))
            for document in json_data:
                if ("_id", self._id) in document.items():
                    document[key] = value
                    break
            else:
                json_data.append({key: value})
            await run_sync(json.dump)(json_data, open(self.collection, "w", encoding="utf-8"), indent=4, ensure_ascii=True)

    async def set_many(self, data: dict):
        if mongo:
            await run_sync(self.collection.update_many)({"_id": self._id}, {"$set": data}, upsert=True)
        else:
            if not os.path.exists(self.collection):
                json_file = await run_sync(open)(self.collection, "w", encoding="utf-8")
                await run_sync(json_file.write)("[]")
                await run_sync(json_file.close)()
            json_data = await run_sync(json.load)(open(self.collection, encoding="utf-8"))
            for document in json_data:
                document: dict
                if ("_id", self._id) in document.items():
                    document.update(data)
            else:
                json_data.append(data)
            await run_sync(json.dump)(json_data, open(self.collection, "w", encoding="utf-8"), indent=4, ensure_ascii=True)

    async def del_data(self, key):
        key = key.replace(".", "_")
        if mongo:
            await run_sync(self.collection.update_one)({"_id": self._id}, {"$unset": {key: 1}})
        else:
            if not os.path.exists(self.collection):
                json_file = await run_sync(open)(self.collection, "w", encoding="utf-8")
                await run_sync(json_file.write)("[]")
                await run_sync(json_file.close)()
            json_data = await run_sync(json.load)(open(self.collection, encoding="utf-8"))
            for document in json_data:
                document: dict
                if ("_id", self._id) in document.items():
                    if key in document:
                        del document[key]

    async def delete(self):
        """
        慎用 删除集合中的文档

        :return:
        """
        await run_sync(self.collection.delete_one)({"id": self._id})

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
