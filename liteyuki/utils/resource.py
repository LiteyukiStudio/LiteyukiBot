import os
import shutil

import nonebot
import yaml
from typing import Any

from liteyuki.utils.data import LiteModel

_loaded_resource_packs: list["ResourceMetadata"] = []  # 按照加载顺序排序
temp_resource_root = "data/liteyuki/resources"


class ResourceMetadata(LiteModel):
    name: str = "Unknown"
    version: str = "0.0.1"
    description: str = "Unknown"
    path: str


def load_resource_from_dir(path: str):
    """
    把资源包按照文件相对路径复制到运行临时文件夹data/liteyuki/resources
    Args:
        path:  资源文件夹
    Returns:
    """
    if os.path.exists(os.path.join(path, "metadata.yml")):
        with open(os.path.join(path, "metadata.yml"), "r", encoding="utf-8") as f:
            metadata = yaml.safe_load(f)
    else:
        # 没有metadata.yml文件，不是一个资源包
        return
    for root, dirs, files in os.walk(path):
        for file in files:
            relative_path = os.path.relpath(os.path.join(root, file), path)
            copy_file(os.path.join(root, file), os.path.join(temp_resource_root, relative_path))
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
    resource_relative_path = os.path.join(temp_resource_root, path)
    if os.path.exists(resource_relative_path):
        return os.path.abspath(resource_relative_path) if abs_path else resource_relative_path
    else:
        return default


def get_files(path: str, abs_path: bool = False) -> list[str]:
    """
    获取资源包中一个文件夹的所有文件
    Args:
        abs_path:
        path: 文件夹相对路径
    Returns: 文件绝对路径
    """
    resource_relative_path = os.path.join(temp_resource_root, path)
    if os.path.exists(resource_relative_path):
        return [os.path.abspath(os.path.join(resource_relative_path, file)) if abs_path else os.path.join(resource_relative_path, file) for file in
                os.listdir(resource_relative_path)]
    else:
        return []


def get_loaded_resource_packs() -> list[ResourceMetadata]:
    """
    获取已加载的资源包
    Returns: 资源包列表
    """
    return _loaded_resource_packs


def copy_file(src, dst):
    # 获取目标文件的目录
    dst_dir = os.path.dirname(dst)
    # 如果目标目录不存在，创建它
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    # 复制文件
    shutil.copy(src, dst)


def load_resources():
    """用于外部主程序调用的资源加载函数
    Returns:
    """
    # 加载默认资源和语言
    # 清空临时资源包路径data/liteyuki/resources
    _loaded_resource_packs.clear()
    if os.path.exists(temp_resource_root):
        shutil.rmtree(temp_resource_root)
    os.makedirs(temp_resource_root, exist_ok=True)

    standard_resource_path = "liteyuki/resources"
    load_resource_from_dir(standard_resource_path)
    # 加载其他资源包
    if os.path.exists("resources"):
        for resource in os.listdir("resources"):
            load_resource_from_dir(os.path.join("resources", resource))
