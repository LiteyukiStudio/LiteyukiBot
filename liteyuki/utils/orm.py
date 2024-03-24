import os
import pickle
import sqlite3
from types import NoneType
from typing import Any

import nonebot
from pydantic import BaseModel, Field


class LiteModel(BaseModel):
    """轻量级模型基类
    类型注解统一使用Python3.9的PEP585标准，如需使用泛型请使用typing模块的泛型类型
    不允许使用id, table_name以及其他SQLite关键字作为字段名，不允许使用JSON和ID，必须指定默认值，且默认值类型必须与字段类型一致
    """
    __ID__: int = Field(None, alias='id')
    __TABLE_NAME__: str = Field(None, alias='table_name')


class Database:
    TYPE_MAPPING = {
            int     : "INTEGER",
            float   : "REAL",
            str     : "TEXT",
            bool    : "INTEGER",
            bytes   : "BLOB",
            NoneType: "NULL",

            dict    : "BLOB",  # LITEYUKIDICT{key_name}
            list    : "BLOB",  # LITEYUKILIST{key_name}
            tuple   : "BLOB",  # LITEYUKITUPLE{key_name}
            set     : "BLOB",  # LITEYUKISET{key_name}
    }

    # 基础类型
    BASIC_TYPE = [int, float, str, bool, bytes, NoneType]
    # 可序列化类型
    ITERABLE_TYPE = [dict, list, tuple, set]

    LITEYUKI = "LITEYUKI"

    # 字段前缀映射，默认基础类型为""
    FIELD_PREFIX_MAPPING = {
            dict           : f"{LITEYUKI}DICT",
            list           : f"{LITEYUKI}LIST",
            tuple          : f"{LITEYUKI}TUPLE",
            set            : f"{LITEYUKI}SET",
            type(LiteModel): f"{LITEYUKI}MODEL"
    }

    def __init__(self, db_name: str):
        if not os.path.exists(os.path.dirname(db_name)):
            os.makedirs(os.path.dirname(db_name))
        self.conn = sqlite3.connect(db_name)  # 连接对象
        self.conn.row_factory = sqlite3.Row  # 以字典形式返回查询结果
        self.cursor = self.conn.cursor()  # 游标对象

    def auto_migrate(self, *args: LiteModel):
        """
        自动迁移模型
        Args:
            *args: 模型类实例化对象，支持空默认值，不支持嵌套迁移

        Returns:

        """
        for model in args:
            if not model.__TABLE_NAME__:
                raise ValueError(f"数据模型{model.__class__.__name__}未提供表名")

            # 若无则创建表
            self.cursor.execute(
                f'CREATE TABLE IF NOT EXISTS {model.__TABLE_NAME__} (id INTEGER PRIMARY KEY AUTOINCREMENT)'
            )

            # 获取表结构
            new_fields, new_stored_types = (
                    zip(
                        *[(self._get_stored_field_prefix(model.__getattribute__(field)) + field, self._get_stored_type(model.__getattribute__(field)))
                          for field in model.__annotations__]
                    )
            )

            # 原有的字段列表
            existing_fields = self.cursor.execute(f'PRAGMA table_info({model.__TABLE_NAME__})').fetchall()
            existing_types = [field['name'] for field in existing_fields]

            # 检测缺失字段，由于SQLite是动态类型，所以不需要检测类型
            for n_field, n_type in zip(new_fields, new_stored_types):
                if n_field not in existing_types:
                    nonebot.logger.debug(f'ALTER TABLE {model.__TABLE_NAME__} ADD COLUMN {n_field} {n_type}')
                    self.cursor.execute(
                        f'ALTER TABLE {model.__TABLE_NAME__} ADD COLUMN {n_field} {n_type}'
                    )

            # 检测多余字段进行删除
            for e_field in existing_types:
                if e_field not in new_fields and e_field not in ['id']:
                    nonebot.logger.debug(f'ALTER TABLE {model.__TABLE_NAME__} DROP COLUMN {e_field}')
                    self.cursor.execute(
                        f'ALTER TABLE {model.__TABLE_NAME__} DROP COLUMN {e_field}'
                    )

        self.conn.commit()

    def save(self, *args: LiteModel) -> [int | tuple[int, ...]]:
        """
        保存或更新模型
        Args:
            *args: 模型类实例化对象，支持空默认值，不支持嵌套迁移
        Returns:

        """
        ids = []
        for model in args:
            if not model.__TABLE_NAME__:
                raise ValueError(f"数据模型{model.__class__.__name__}未提供表名")
            if not self.cursor.execute(f'PRAGMA table_info({model.__TABLE_NAME__})').fetchall():
                raise ValueError(f"数据表{model.__TABLE_NAME__}不存在，请先迁移{model.__class__.__name__}模型")

            stored_fields, stored_values = [], []
            for r_field in model.__annotations__:
                r_value = model.__getattribute__(r_field)
                stored_fields.append(self._get_stored_field_prefix(r_value) + r_field)

                if type(r_value) in Database.BASIC_TYPE:
                    # int str float bool bytes NoneType
                    stored_values.append(r_value)

                elif type(r_value) in Database.ITERABLE_TYPE:
                    # dict list tuple set
                    stored_values.append(pickle.dumps(self._flat_save(r_value)))

                elif isinstance(r_value, LiteModel):
                    # LiteModel TABLE_NAME:ID
                    stored_values.append(f"{r_value.__TABLE_NAME__}:{self.save(r_value)}")

                else:
                    raise ValueError(f"不支持的数据类型{type(r_value)}")
            nonebot.logger.debug(f"INSERT OR REPLACE INTO {model.__TABLE_NAME__} ({','.join(stored_fields)}) VALUES ({','.join([_ for _ in stored_values])})")
            self.cursor.execute(
                f"INSERT OR REPLACE INTO {model.__TABLE_NAME__} ({','.join(stored_fields)}) VALUES ({','.join(['?' for _ in stored_values])})",
                stored_values
            )
            ids.append(self.cursor.lastrowid)
            self.conn.commit()
        return tuple(ids) if len(ids) > 1 else ids[0]

        # 检测id字段是否有1，有则更新，无则插入

    def _flat_save(self, obj) -> Any:
        """扁平化存储

        Args:
            obj: 需要存储的对象

        Returns:
            存储的字节流
        """
        # TODO 递归扁平化存储
        if type(obj) in Database.ITERABLE_TYPE:
            for i, item in enumerate(obj) if type(obj) in [list, tuple, set] else obj.items():
                if type(item) in Database.BASIC_TYPE:
                    continue
                elif type(item) in Database.ITERABLE_TYPE:
                    obj[i] = pickle.dumps(self._flat_save(item))
                elif isinstance(item, LiteModel):
                    obj[i] = f"{item.__TABLE_NAME__}:{self.save(item)}"
                else:
                    raise ValueError(f"不支持的数据类型{type(item)}")
        else:
            raise ValueError(f"不支持的数据类型{type(obj)}")

    @staticmethod
    def _get_stored_field_prefix(value) -> str:
        """获取存储字段前缀，一定在后加上字段名

        LiteModel -> LITEYUKIID

        dict -> LITEYUKIDICT

        list -> LITEYUKILIST

        tuple -> LITEYUKITUPLE

        set -> LITEYUKISET

        * -> ""
        Args:
            value: 储存的值

        Returns:
            Sqlite3存储字段
        """
        return Database.FIELD_PREFIX_MAPPING.get(type(value), "")

    @staticmethod
    def _get_stored_type(value) -> str:
        """获取存储类型

        Args:
            value: 储存的值

        Returns:
            Sqlite3存储类型
        """
        return Database.TYPE_MAPPING.get(type(value), "TEXT")
