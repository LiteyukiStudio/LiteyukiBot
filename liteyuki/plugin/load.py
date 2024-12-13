# -*- coding: utf-8 -*-
"""
Copyright (C) 2020-2024 LiteyukiStudio. All Rights Reserved 

@Time    : 2024/7/23 下午11:59
@Author  : snowykami
@Email   : snowykami@outlook.com
@File    : load.py
@Software: PyCharm
"""
import os
import traceback
from importlib import import_module
from pathlib import Path
from typing import Optional

from liteyuki.log import logger
from liteyuki.plugin.model import Plugin, PluginMetadata, PluginType
from liteyuki.utils import path_to_module_name

_plugins: dict[str, Plugin] = {}

__all__ = [
    "load_plugin",
    "load_plugins",
    "_plugins",
]


def load_plugin(module_path: str | Path) -> Optional[Plugin]:
    """加载单个插件，可以是本地插件或是通过 `pip` 安装的插件。

    参数:
        module_path: 插件名称 `path.to.your.plugin`
        或插件路径 `pathlib.Path(path/to/your/plugin)`
    """
    module_path = (
        path_to_module_name(Path(module_path))
        if isinstance(module_path, Path)
        else module_path
    )
    try:
        module = import_module(module_path)
        _plugins[module.__name__] = Plugin(
            name=module.__name__,
            module=module,
            module_name=module_path,
        )
        if module.__dict__.get("__plugin_metadata__", None):
            metadata: "PluginMetadata" = module.__dict__["__plugin_metadata__"]
            display_name = module.__name__.split(".")[-1]
        elif module.__dict__.get("__liteyuki_plugin_meta__", None):
            metadata: "PluginMetadata" = module.__dict__["__liteyuki_plugin_meta__"]
            display_name = format_display_name(
                f"{metadata.name}({module.__name__.split('.')[-1]})", metadata.type
            )
        elif module.__dict__.get("__plugin_meta__", None):
            metadata: "PluginMetadata" = module.__dict__["__plugin_meta__"]
            display_name = format_display_name(
                f"{metadata.name}({module.__name__.split('.')[-1]})", metadata.type
            )
        else:
            logger.opt(colors=True).warning(
                f'The metadata of Liteyuki plugin "{module.__name__}" is not specified, use empty.'
            )

            metadata = PluginMetadata(
                name=module.__name__,
            )
            display_name = module.__name__.split(".")[-1]

        _plugins[module.__name__].metadata = metadata

        logger.opt(colors=True).success(
            f'Succeeded to load liteyuki plugin "{display_name}"'
        )
        return _plugins[module.__name__]

    except Exception as e:
        logger.opt(colors=True).success(
            f'Failed to load liteyuki plugin "<r>{module_path}</r>"'
        )
        traceback.print_exc()
        return None


def load_plugins(*plugin_dir: str, ignore_warning: bool = True) -> set[Plugin]:
    """导入文件夹下多个插件

    参数:
        plugin_dir: 文件夹路径
        ignore_warning: 是否忽略警告，通常是目录不存在或目录为空
    """
    plugins = set()
    for dir_path in plugin_dir:
        # 遍历每一个文件夹下的py文件和包含__init__.py的文件夹，不递归
        if not os.path.exists(dir_path):
            if not ignore_warning:
                logger.warning(f"Plugins dir '{dir_path}' does not exist.")
            continue

        if not os.listdir(dir_path):
            if not ignore_warning:
                logger.warning(f"Plugins dir '{dir_path}' is empty.")
            continue

        if not os.path.isdir(dir_path):
            if not ignore_warning:
                logger.warning(f"Plugins dir '{dir_path}' is not a directory.")
            continue

        for f in os.listdir(dir_path):
            path = Path(os.path.join(dir_path, f))

            module_name = None
            if os.path.isfile(path) and f.endswith(".py") and f != "__init__.py":
                module_name = f"{path_to_module_name(Path(dir_path))}.{f[:-3]}"

            elif os.path.isdir(path) and os.path.exists(
                os.path.join(path, "__init__.py")
            ):
                module_name = path_to_module_name(path)

            if module_name:
                load_plugin(module_name)
                if _plugins.get(module_name):
                    plugins.add(_plugins[module_name])
    return plugins


def format_display_name(display_name: str, plugin_type: PluginType) -> str:
    """
    设置插件名称颜色，根据不同类型插件设置颜色
    Args:
        display_name: 插件名称
        plugin_type: 插件类型

    Returns:
        str: 设置后的插件名称 <y>name</y>
    """
    color = "y"
    match plugin_type:
        case PluginType.APPLICATION:
            color = "m"
        case PluginType.TEST:
            color = "g"
        case PluginType.MODULE:
            color = "e"
        case PluginType.SERVICE:
            color = "c"

    return f"<{color}>{display_name} [{plugin_type.name}]</{color}>"
