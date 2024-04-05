import os

import nonebot
import yaml
from typing import Any

from liteyuki.utils.data import LiteModel

_resource_data = {}
_loaded_resource_packs = []  # 按照加载顺序排序


class ResourceMetadata(LiteModel):
    name: str = "Unknown"
    version: str = "0.0.1"
    description: str = "Unknown"
    path: str


def load_resource_from_dir(path: str):
    """
    把资源包按照文件相对路径加载到资源包中，后加载的优先级更高，顺便加载语言
    Args:
        path:  资源文件夹

    Returns:

    """
    for root, dirs, files in os.walk(path):
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), path).replace("\\", "/")
            abs_path = os.path.join(root, file).replace("\\", "/")
            _resource_data[relative_path] = abs_path
    if os.path.exists(os.path.join(path, "metadata.yml")):
        with open(os.path.join(path, "metadata.yml"), "r", encoding="utf-8") as f:
            metadata = yaml.safe_load(f)
    else:
        # 没有metadata.yml文件，不是一个资源包
        return
    metadata["path"] = path
    if os.path.exists(os.path.join(path, "lang")):
        from liteyuki.utils.language import load_from_dir
        load_from_dir(os.path.join(path, "lang"))
    _loaded_resource_packs.append(ResourceMetadata(**metadata))


def get_path(path: str, abs_path: bool = False, default: Any = None) -> str | Any:
    """
    获取资源包中的文件
    Args:
        abs_path: 是否返回绝对路径
        default: 默认
        path: 文件相对路径
    Returns: 文件绝对路径
    """
    return _resource_data.get(path, default) if not abs_path else os.path.abspath(_resource_data.get(path, default))


def get_files(path: str, abs_path: bool = False) -> list[str]:
    """
    获取资源包中一个文件夹的所有文件
    Args:
        abs_path:
        path: 文件夹相对路径
    Returns: 文件绝对路径
    """
    return [os.path.abspath(file) for file in _resource_data if file.startswith(path)] if abs_path else [
            file for file in _resource_data if file.startswith(path)]
