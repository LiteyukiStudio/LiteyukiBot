import os
from typing import Any

from keyvalue_sqlite import KeyValueSqlite
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent

DB_PATH = 'data/liteyuki'


class Data:
    def __init__(self, db_name: str = None, table_name: str = None, event: MessageEvent = None):
        """

        :param db_name: DB Name, such as users/groups/globals/plugins
        :param table_name: Table Name, such as target_id, not start with '_'
        """

        if event is not None:
            if isinstance(event, PrivateMessageEvent):
                db_name = 'users'
                table_name = str(event.user_id)
            else:
                event: GroupMessageEvent
                db_name = 'groups'
                table_name = str(event.group_id)

        if table_name.isalnum():
            table_name = '_' + table_name
        self.db = KeyValueSqlite(db_path=os.path.join(DB_PATH, str(db_name) + ".db"), table_name=table_name)

    def get(self, key: str, default: Any = None) -> Any:
        """Get data from table
        :param key: key
        :param default: if there is no key, return this
        :return:
        """
        return self.db.get(key, default)

    def get_many(self, key_set: set) -> dict[str, Any]:
        """Get many data from table by a key set

        :param key_set:
        :return: {key: val,}
        """
        return self.db.get_many(key_set)

    def set(self, key: str, val: Any):
        """Store data to table
        :param key: key
        :param val: value
        :return:
        """
        return self.db.set(key, val)

    def set_many(self, data: dict):
        """Store many data to table
        :param data: {key: val,}
        :return:
        """
        for key, val in data.items():
            self.set(key, val)

    def remove(self, key: str):
        """Remove data from table

        :param key: key
        :return:
        """
        return self.db.remove(key, ignore_missing_key=True)

    def detect(self, key: str) -> bool:
        """Detect if the key in the table

        :param key: key
        :return:
        """
        return self.db.has_key(key)


config_db = Data("globals", "config")
