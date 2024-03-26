import copy
import json
import os
import pickle
import sqlite3
import types
from types import NoneType
from collections.abc import Iterable
from pydantic import BaseModel, Field
from typing import Any

LOG_OUT = True


def log(*args, **kwargs):
    if LOG_OUT:
        print(*args, **kwargs)


class LiteModel(BaseModel):
    TABLE_NAME: str = None
    id: int = None


class Database:
    def __init__(self, db_name: str):

        if os.path.dirname(db_name) != "" and not os.path.exists(os.path.dirname(db_name)):
            os.makedirs(os.path.dirname(db_name))

        self.db_name = db_name
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()

    def first(self, model: LiteModel, condition: str, *args: Any, default: Any = None) -> LiteModel | Any | None:
        """查询第一个
        Args:
            model: 数据模型实例
            condition: 查询条件，不给定则查询所有
            *args: 参数化查询参数
            default: 默认值

        Returns:

        """
        all_results = self.all(model, condition, *args, default=default)
        return all_results[0] if all_results else default

    def all(self, model: LiteModel, condition: str = "", *args: Any, default: Any = None) -> list[LiteModel] | list[Any] | None:
        """查询所有
        Args:
            model: 数据模型实例
            condition: 查询条件，不给定则查询所有
            *args: 参数化查询参数
            default: 默认值

        Returns:

        """
        table_name = model.TABLE_NAME
        model_type = type(model)
        if not table_name:
            raise ValueError(f"数据模型{model_type.__name__}未提供表名")

        condition = f"WHERE {condition}"

        results = self.cursor.execute(f"SELECT * FROM {table_name} {condition}", args).fetchall()
        fields = [description[0] for description in self.cursor.description]
        if not results:
            return default
        else:
            return [model_type(**self._load(dict(zip(fields, result)))) for result in results]

    def upsert(self, *args: LiteModel):
        """增/改操作
        Args:
            *args:

        Returns:
        """
        table_list = [item[0] for item in self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        for model in args:
            if not model.TABLE_NAME:
                raise ValueError(f"数据模型 {model.__class__.__name__} 未提供表名")
            elif model.TABLE_NAME not in table_list:
                raise ValueError(f"数据模型 {model.__class__.__name__} 的表 {model.TABLE_NAME} 不存在，请先迁移")
            else:
                self._save(model.model_dump(by_alias=True))

    def _save(self, obj: Any) -> Any:
        # obj = copy.deepcopy(obj)
        if isinstance(obj, dict):
            table_name = obj.get("TABLE_NAME")
            row_id = obj.get("id")
            new_obj = {}
            for field, value in obj.items():
                if isinstance(value, self.ITERABLE_TYPE):
                    new_obj[self._get_stored_field_prefix(value) + field] = self._save(value)  # self._save(value)  # -> bytes
                elif isinstance(value, self.BASIC_TYPE):
                    new_obj[field] = value
                else:
                    raise ValueError(f"数据模型{table_name}包含不支持的数据类型，字段：{field} 值：{value} 值类型：{type(value)}")
            if table_name:
                fields, values = [], []
                for n_field, n_value in new_obj.items():
                    if n_field not in ["TABLE_NAME", "id"]:
                        fields.append(n_field)
                        values.append(n_value)
                # 移除TABLE_NAME和id
                fields = list(fields)
                values = list(values)
                if row_id is not None:
                    # 如果 _id 不为空，将 'id' 插入到字段列表的开始
                    fields.insert(0, 'id')
                    # 将 _id 插入到值列表的开始
                    values.insert(0, row_id)
                fields = ', '.join([f'"{field}"' for field in fields])
                placeholders = ', '.join('?' for _ in values)
                self.cursor.execute(f"INSERT OR REPLACE INTO {table_name}({fields}) VALUES ({placeholders})", tuple(values))
                self.conn.commit()
                foreign_id = self.cursor.execute("SELECT last_insert_rowid()").fetchone()[0]
                return f"{self.FOREIGN_KEY_PREFIX}{foreign_id}@{table_name}"  # -> FOREIGN_KEY_123456@{table_name} id@{table_name}
            else:
                return pickle.dumps(new_obj)  # -> bytes
        elif isinstance(obj, (list, set, tuple)):
            obj_type = type(obj)  # 到时候转回去
            new_obj = []
            for item in obj:
                if isinstance(item, self.ITERABLE_TYPE):
                    new_obj.append(self._save(item))
                elif isinstance(item, self.BASIC_TYPE):
                    new_obj.append(item)
                else:
                    raise ValueError(f"数据模型包含不支持的数据类型，值：{item} 值类型：{type(item)}")
            return pickle.dumps(obj_type(new_obj))  # -> bytes
        else:
            raise ValueError(f"数据模型包含不支持的数据类型，值：{obj} 值类型：{type(obj)}")

    def _load(self, obj: Any) -> Any:

        if isinstance(obj, dict):

            new_obj = {}

            for field, value in obj.items():

                field: str

                if field.startswith(self.BYTES_PREFIX):

                    new_obj[field.replace(self.BYTES_PREFIX, "")] = self._load(pickle.loads(value))

                elif field.startswith(self.FOREIGN_KEY_PREFIX):

                    new_obj[field.replace(self.FOREIGN_KEY_PREFIX, "")] = self._load(self._get_foreign_data(value))

                else:
                    new_obj[field] = value
            return new_obj
        elif isinstance(obj, (list, set, tuple)):

            print(" - Load as List")

            new_obj = []
            for item in obj:

                print("   - Loading Item", item)

                if isinstance(item, bytes):

                    # 对bytes进行尝试解析，解析失败则返回原始bytes
                    try:
                        new_obj.append(self._load(pickle.loads(item)))
                    except Exception as e:
                        new_obj.append(self._load(item))

                    print("     - Load as Bytes | Result:", new_obj[-1])

                elif isinstance(item, str) and item.startswith(self.FOREIGN_KEY_PREFIX):
                    new_obj.append(self._load(self._get_foreign_data(item)))
                else:
                    new_obj.append(self._load(item))
            return new_obj
        else:
            return obj

    def delete(self, model: LiteModel, condition: str, *args: Any):
        pass

    def auto_migrate(self, *args: LiteModel):

        """
        自动迁移模型
        Args:
            *args: 模型类实例化对象，支持空默认值，不支持嵌套迁移

        Returns:

        """
        for model in args:
            if not model.TABLE_NAME:
                raise ValueError(f"数据模型{type(model).__name__}未提供表名")

            # 若无则创建表
            self.cursor.execute(
                f'CREATE TABLE IF NOT EXISTS "{model.TABLE_NAME}" (id INTEGER PRIMARY KEY AUTOINCREMENT)'
            )

            # 获取表结构,field -> SqliteType
            new_structure = {}
            for n_field, n_value in model.model_dump(by_alias=True).items():
                if n_field not in ["TABLE_NAME", "id"]:
                    new_structure[self._get_stored_field_prefix(n_value) + n_field] = self._get_stored_type(n_value)

            # 原有的字段列表
            existing_structure = dict([(column[1], column[2]) for column in self.cursor.execute(f'PRAGMA table_info({model.TABLE_NAME})').fetchall()])
            # 检测缺失字段，由于SQLite是动态类型，所以不需要检测类型
            for n_field, n_type in new_structure.items():
                if n_field not in existing_structure.keys() and n_field.lower() not in ["id", "table_name"]:
                    self.cursor.execute(
                        f'ALTER TABLE "{model.TABLE_NAME}" ADD COLUMN "{n_field}" {n_type}'
                    )

            # 检测多余字段进行删除
            for e_field in existing_structure.keys():
                if e_field not in new_structure.keys() and e_field.lower() not in ['id']:
                    self.cursor.execute(
                        f'ALTER TABLE "{model.TABLE_NAME}" DROP COLUMN "{e_field}"'
                    )

        self.conn.commit()
        # 已完成

    def _get_stored_field_prefix(self, value) -> str:
        """根据类型获取存储字段前缀，一定在后加上字段名
        * -> ""
        Args:
            value: 储存的值

        Returns:
            Sqlite3存储字段
        """

        if isinstance(value, LiteModel) or isinstance(value, dict) and "TABLE_NAME" in value:
            return self.FOREIGN_KEY_PREFIX
        elif type(value) in self.ITERABLE_TYPE:
            return self.BYTES_PREFIX
        return ""

    def _get_stored_type(self, value) -> str:
        """获取存储类型

        Args:
            value: 储存的值

        Returns:
            Sqlite3存储类型
        """
        if isinstance(value, dict) and "TABLE_NAME" in value:
            # 是一个模型字典，储存外键
            return "INTEGER"
        return self.TYPE_MAPPING.get(type(value), "TEXT")

    def _get_foreign_data(self, foreign_value: str) -> dict:
        """
        获取外键数据
        Args:
            foreign_value:

        Returns:

        """
        foreign_value = foreign_value.replace(self.FOREIGN_KEY_PREFIX, "")
        table_name = foreign_value.split("@")[-1]
        foreign_id = foreign_value.split("@")[0]
        fields = [description[1] for description in self.cursor.execute(f"PRAGMA table_info({table_name})").fetchall()]
        result = self.cursor.execute(f"SELECT * FROM {table_name} WHERE id = ?", (foreign_id,)).fetchone()
        return dict(zip(fields, result))

    TYPE_MAPPING = {
            int      : "INTEGER",
            float    : "REAL",
            str      : "TEXT",
            bool     : "INTEGER",
            bytes    : "BLOB",
            NoneType : "NULL",
            # dict     : "TEXT",
            # list     : "TEXT",
            # tuple    : "TEXT",
            # set      : "TEXT",

            dict     : "BLOB",  # LITEYUKIDICT{key_name}
            list     : "BLOB",  # LITEYUKILIST{key_name}
            tuple    : "BLOB",  # LITEYUKITUPLE{key_name}
            set      : "BLOB",  # LITEYUKISET{key_name}
            LiteModel: "INTEGER"  # FOREIGN_KEY_{table_name}
    }

    # 基础类型
    BASIC_TYPE = (int, float, str, bool, bytes, NoneType)
    # 可序列化类型
    ITERABLE_TYPE = (dict, list, tuple, set, LiteModel)

    # 外键前缀
    FOREIGN_KEY_PREFIX = "FOREIGN_KEY_"
    # 转换为的字节前缀
    BYTES_PREFIX = "PICKLE_BYTES_"


def check_sqlite_keyword(name):
    sqlite_keywords = [
            "ABORT", "ACTION", "ADD", "AFTER", "ALL", "ALTER", "ANALYZE", "AND", "AS", "ASC",
            "ATTACH", "AUTOINCREMENT", "BEFORE", "BEGIN", "BETWEEN", "BY", "CASCADE", "CASE",
            "CAST", "CHECK", "COLLATE", "COLUMN", "COMMIT", "CONFLICT", "CONSTRAINT", "CREATE",
            "CROSS", "CURRENT_DATE", "CURRENT_TIME", "CURRENT_TIMESTAMP", "DATABASE", "DEFAULT",
            "DEFERRABLE", "DEFERRED", "DELETE", "DESC", "DETACH", "DISTINCT", "DROP", "EACH",
            "ELSE", "END", "ESCAPE", "EXCEPT", "EXCLUSIVE", "EXISTS", "EXPLAIN", "FAIL", "FOR",
            "FOREIGN", "FROM", "FULL", "GLOB", "GROUP", "HAVING", "IF", "IGNORE", "IMMEDIATE",
            "IN", "INDEX", "INDEXED", "INITIALLY", "INNER", "INSERT", "INSTEAD", "INTERSECT",
            "INTO", "IS", "ISNULL", "JOIN", "KEY", "LEFT", "LIKE", "LIMIT", "MATCH", "NATURAL",
            "NO", "NOT", "NOTNULL", "NULL", "OF", "OFFSET", "ON", "OR", "ORDER", "OUTER", "PLAN",
            "PRAGMA", "PRIMARY", "QUERY", "RAISE", "RECURSIVE", "REFERENCES", "REGEXP", "REINDEX",
            "RELEASE", "RENAME", "REPLACE", "RESTRICT", "RIGHT", "ROLLBACK", "ROW", "SAVEPOINT",
            "SELECT", "SET", "TABLE", "TEMP", "TEMPORARY", "THEN", "TO", "TRANSACTION", "TRIGGER",
            "UNION", "UNIQUE", "UPDATE", "USING", "VACUUM", "VALUES", "VIEW", "VIRTUAL", "WHEN",
            "WHERE", "WITH", "WITHOUT"
    ]
    return True
    # if name.upper() in sqlite_keywords:
    #     raise ValueError(f"'{name}' 是SQLite保留字，不建议使用，请更换名称")
