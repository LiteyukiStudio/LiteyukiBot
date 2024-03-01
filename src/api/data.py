import json
import sqlite3
from abc import ABC
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

BaseIterable = list | tuple | set | dict


class LiteModel(BaseModel):
    pass


class BaseORMAdapter(ABC):
    def __init__(self):
        pass

    def auto_migrate(self, *args, **kwargs):
        """自动迁移

        Returns:

        """
        raise NotImplementedError

    def save(self, *args, **kwargs):
        """存储数据

        Returns:

        """
        raise NotImplementedError

    def first(self, *args, **kwargs):
        """查询第一条数据

        Returns:

        """
        raise NotImplementedError

    def all(self, *args, **kwargs):
        """查询所有数据

        Returns:

        """
        raise NotImplementedError

    def delete(self, *args, **kwargs):
        """删除数据

        Returns:

        """
        raise NotImplementedError

    def update(self, *args, **kwargs):
        """更新数据

        Returns:

        """
        raise NotImplementedError


class SqliteORMAdapter(BaseORMAdapter):
    type_map = {
            # default: TEXT
            str  : 'TEXT',
            int  : 'INTEGER',
            float: 'REAL',
            bool : 'INTEGER',
            list : 'TEXT'
    }

    def __init__(self, db_name: str):
        super().__init__()
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()

    def auto_migrate(self, *args: LiteModel):
        """自动迁移，检测新模型字段和原有表字段的差异，如有差异自动增删新字段

        Args:
            *args:

        Returns:

        """
        for model in args:
            # 检测并创建表
            self.cursor.execute(f'CREATE TABLE IF NOT EXISTS {model.__name__}(id INTEGER PRIMARY KEY AUTOINCREMENT)')
            # 获取表字段
            self.cursor.execute(f'PRAGMA table_info({model.__name__})')
            table_fields = self.cursor.fetchall()
            table_fields = [field[1] for field in table_fields]

            # 获取模型字段
            model_fields = model.__dict__.keys()

            # 获取模型字段类型
            model_types = [self.type_map.get(type(model.__dict__[field]), 'TEXT') for field in model_fields]

            # 获取模型字段默认值
            model_defaults = [model.__dict__[field] for field in model_fields]

            # 检测新字段
            for field, type_, default in zip(model_fields, model_types, model_defaults):
                if field not in table_fields:
                    self.cursor.execute(f'ALTER TABLE {model.__name__} ADD COLUMN {field} {type_} DEFAULT {default}')

            # 检测多余字段
            for field in table_fields:
                if field not in model_fields:
                    self.cursor.execute(f'ALTER TABLE {model.__name__} DROP COLUMN {field}')

        self.conn.commit()

    def save(self, *models: LiteModel) -> int:
        """存储数据

        Args:
            models: 数据

        Returns:
            id: 数据id，多个数据返回最后一个数据id
        """
        _id = 0
        for model in models:
            table_name = model.__class__.__name__
            key_list = []
            value_list = []
            # 处理外键，添加前缀'$IDFieldName'
            for field, value in model.__dict__.items():
                if isinstance(value, LiteModel):
                    key_list.append(f'$id:{field}')
                    value_list.append(f'{value.__class__.__name__}:{self.save(value)}')
                elif isinstance(value, list | tuple | set):
                    key_list.append(field)
                    value_list.append(json.dumps(value))
                else:
                    key_list.append(field)
                    value_list.append(value)

    def flat(self, data: Iterable) -> Any:
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, dict | list | tuple | set):
                    self.flat(v)
                else:
                    print(k, v)

    def first(self, model: type(LiteModel), *args, **kwargs):
        self.cursor.execute(f'SELECT * FROM {model.__name__} WHERE {args[0]}', args[1])
        return self.convert2dict(model, self.cursor.fetchone())

    def convert2dict(self, data: dict) -> dict | list:
        """将模型转换为dict

        Args:
            data: 数据库查询结果

        Returns:
            模型对象
        """
        for field, value in data.items():
            if field.startswith('$id'):
                # 外键处理
                table_name = value[1:].split('_')[0]
                id_ = value.split('_')[1]
                key_tuple = self.cursor.execute(f'PRAGMA table_info({table_name})').fetchall()
                value_tuple = self.cursor.execute(f'SELECT * FROM {table_name} WHERE id = ?', id_).fetchone()
                field_dict = dict(zip([field[1] for field in key_tuple], value_tuple))
