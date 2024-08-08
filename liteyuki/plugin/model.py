# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/24 上午12:02
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : model.py
@Software: PyCharm
"""
from types import ModuleType
from typing import Optional

from pydantic import BaseModel


class PluginMetadata(BaseModel):
    """
    轻雪插件元数据，由插件编写者提供，name为必填项
    """
    name: str
    description: str = ""
    usage: str = ""
    type: str = ""
    homepage: str = ""
    running_in_main: bool = True    # 是否在主进程运行


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
