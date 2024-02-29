import sqlite3
import uuid
from typing import Any

from pymongo import MongoClient
from pydantic import BaseModel


class LiteModel(BaseModel):
    pass


class BaseORM:

    def __init__(self, *args, **kwargs):
        pass

    def auto_migrate(self, *args, **kwargs):
        """自动迁移数据库
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def save(self, *args, **kwargs):
        """创建数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def update(self, *args, **kwargs):
        """更新数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def delete(self, *args, **kwargs):
        """删除数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def first(self, *args, **kwargs):
        """查询第一条数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def where(self, *args, **kwargs):
        """查询数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError

    def all(self, *args, **kwargs):
        """查询所有数据
        Args:
            *args:
            **kwargs:

        Returns:
        """
        raise NotImplementedError


class SqliteORM(BaseORM):
    """同步sqlite数据库操作"""
    type_map = {
        int: 'INTEGER',
        float: 'REAL',
        str: 'TEXT',
        bool: 'INTEGER',
    }

    def __init__(self, db, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.db = sqlite3.connect(db)

    @staticmethod
    def get_model_table_name(model: type(LiteModel) | LiteModel | str) -> str:
        """获取模型对应的表名"""
        if isinstance(model, str):
            return model
        elif isinstance(model, LiteModel):
            return model.__class__.__name__
        elif isinstance(model, type(LiteModel)):
            return model.__name__

    def auto_migrate(self, *args: type(LiteModel) | LiteModel | str, **kwargs):
        """自动迁移数据库
        Args:
            *args: BaseModel
            **kwargs:
                delete_old_columns: bool = False    # 是否删除旧字段
                add_new_columns: bool = True    # 添加新字段
        Returns:
        """
        for model in args:
            # 获取模型对应的表名
            table_name = self.get_model_table_name(model)

            # 获取表中已有的字段
            existing_columns = set()
            cursor = self.db.execute(f"PRAGMA table_info({table_name})")
            for column_info in cursor.fetchall():
                existing_columns.add(column_info[1])

            # 创建表，如果不存在的话
            self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')

            # 检测模型中的字段并添加新字段，按照类型添加
            for field_name, field_type in model.__annotations__.items():
                if field_name not in existing_columns:
                    self.db.execute(f'ALTER TABLE {table_name} ADD COLUMN {field_name} {self.type_map.get(field_type, "TEXT")}')

            # 提交事务
            self.db.commit()

    def save(self, model: LiteModel) -> int:
        """保存或创建数据，对嵌套模型扁平化处理，加特殊前缀表示为模型，实际储存模型id，嵌套对象单独储存
        Args:
            model: BaseModel
        Returns: id主键
        """
        # 先检测表是否存在，不存在则创建
        table_name = self.get_model_table_name(model)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')

        # 构建插入语句
        column_list = []
        value_list = []
        for key, value in model.dict().items():
            if isinstance(value, LiteModel):
                # 如果是嵌套模型，先保存嵌套模型
                nested_model_id = self.save(value)
                # 保存嵌套模型的id, 以特殊前缀表示为模型
                column_list.append(f'$id_{key}')
                value_list.append(f'{value.__class__.__name__}_{nested_model_id}')
            elif isinstance(value, list):
                # 如果是列表，先保存列表中的所有嵌套模型，有可能有多种类型的嵌套模型
                # 列表内存'ModelType_ModelId'，以特殊前缀表示为模型类型
                nested_model_ids = []
                for nested_model in value:
                    nested_model_id = self.save(nested_model)
                    nested_model_ids.append(f'{nested_model.__class__.__name__}_{nested_model_id}')
                column_list.append(f'$ids_{key}')
                value_list.append(nested_model_ids)

        columns = ', '.join(column_list)
        placeholders = ', '.join(['?' for _ in value_list])
        values = tuple(value_list)
        print(model.dict())
        print(table_name, columns, placeholders, values)

        # 插入数据
        self.db.execute(f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})', values)
        self.db.commit()
        return self.db.execute(f'SELECT last_insert_rowid()').fetchone()[0]

    def where(self, model_type: type(LiteModel) | str, conditions: str, *args, objectify: bool = True) -> list[LiteModel]:
        """查询数据
        Args:
            objectify: bool: 是否将查询结果转换为模型
            model_type: BaseModel
            conditions: str
            *args:
            Returns:
        """
        table_name = self.get_model_table_name(model_type)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')
        return [self._convert_to_model(model_type, item) for item in self.db.execute(f'SELECT * FROM {table_name} WHERE {conditions}', args).fetchall()]

    def first(self, model_type: type(LiteModel) | str, conditions: str, *args, objectify: bool = True):
        """查询第一条数据"""
        table_name = self.get_model_table_name(model_type)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')
        return self._convert_to_model(model_type, self.db.execute(f'SELECT * FROM {table_name} WHERE {conditions}', args).fetchone())

    def all(self, model_type: type(LiteModel) | str, objectify: bool = True):
        """查询所有数据"""
        table_name = self.get_model_table_name(model_type)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')
        return [self._convert_to_model(model_type, item) for item in self.db.execute(f'SELECT * FROM {table_name}').fetchall()]

    def update(self, model_type: type(LiteModel) | str, operation: str, conditions: str, *args):
        """更新数据
        Args:
            model_type: BaseModel
            operation: str: 更新操作
            conditions: str: 查询条件
            *args:
        Returns:
        """
        table_name = self.get_model_table_name(model_type)
        self.db.execute(f'CREATE TABLE IF NOT EXISTS {table_name} (id INTEGER PRIMARY KEY AUTOINCREMENT)')
        self.db.execute(f'UPDATE {table_name} SET {operation} WHERE {conditions}', args)
        self.db.commit()

    def _convert_to_model(self, model_type: type(LiteModel), item: tuple) -> LiteModel:
        """将查询结果转换为模型，处理嵌套模型"""
        # 获取表中已有的字段，再用字段值构建字典
        table_name = self.get_model_table_name(model_type)
        cursor = self.db.execute(f"PRAGMA table_info({table_name})")
        columns = [column_info[1] for column_info in cursor.fetchall()]
        item_dict = dict(zip(columns, item))
        # 遍历字典，处理嵌套模型
        new_item_dict = {}
        for key, value in item_dict.items():
            if key.startswith('$id_'):
                # 处理单个嵌套模型类型时从model_type中获取键
                new_item_dict[key.replace('$id_', '')] = self.first(model_type.__annotations__[key.replace('$id_', '')], 'id = ?', value.split('_')[-1])
            elif key.startswith('$ids_'):
                # 处理多个嵌套模型类型使用eval获取数据库对应索引的键
                new_item_dict[key.replace('$ids_', '')] = [self.first(eval(type_id.split('_')[0]), 'id = ?', type_id.split('_')[-1]) for type_id in value]
            else:
                new_item_dict[key] = value

        return model_type(**new_item_dict)
