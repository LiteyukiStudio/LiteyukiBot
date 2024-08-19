# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/24 上午12:02
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : model.py
@Software: PyCharm
"""
from enum import Enum
from types import ModuleType
from typing import Any, Optional

from pydantic import BaseModel


class PluginType(Enum):
    """
    插件类型枚举值
    """
    APPLICATION = "application"
    """应用端：例如NoneBot"""

    SERVICE = "service"
    """服务端：例如AI绘画后端"""

    MODULE = "module"
    """模块：导出对象给其他插件使用"""

    UNCLASSIFIED = "unclassified"
    """未分类：默认值"""

    TEST = "test"
    """测试：测试插件"""


class PluginMetadata(BaseModel):
    """
    轻雪插件元数据，由插件编写者提供，name为必填项
    Attributes:
    ----------

    name: str
        插件名称
    description: str
        插件描述
    usage: str
        插件使用方法
    type: str
        插件类型
    author: str
        插件作者
    homepage: str
        插件主页
    extra: dict[str, Any]
        额外信息
    """
    name: str
    description: str = ""
    usage: str = ""
    type: PluginType = PluginType.UNCLASSIFIED
    author: str = ""
    homepage: str = ""
    extra: dict[str, Any] = {}


class Plugin(BaseModel):
    """
    存储插件信息
    """
    model_config = {
            'arbitrary_types_allowed': True
    }
    name: str
    """插件名称 例如plugin_loader"""
    module: ModuleType
    """插件模块对象"""
    module_name: str
    """点分割模块路径 例如a.b.c"""
    metadata: Optional[PluginMetadata] = None

    def __hash__(self):
        return hash(self.module_name)
