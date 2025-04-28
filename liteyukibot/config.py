import json
import os
import tomllib
from typing import Any

import yaml  # type: ignore[import]

type RawConfig = dict[str, Any]

def load_from_yaml(file_path: str) -> RawConfig:
    """从yaml文件中加载配置并返回字典
    
    Args:
        file_path (str): yaml文件路径
    
    Returns:
        dict[str, Any]: 配置字典
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)
    
def load_from_json(file_path: str) -> RawConfig:
    """从json文件中加载配置并返回字典

    Args:
        file_path (str): json文件路径

    Returns:
        dict[str, Any]: 配置字典
    """
    
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)
    
def load_from_toml(file_path: str) -> RawConfig:
    """从toml文件中加载配置并返回字典

    Args:
        file_path (str): toml文件路径

    Returns:
        dict[str, Any]: 配置字典
    """
    with open(file_path, "rb") as file:
        return tomllib.load(file)

def merge_dicts(base: RawConfig, new: RawConfig) -> RawConfig:
    """递归合并两个字典

    Args:
        base (dict[str, Any]): 原始字典
        new (dict[str, Any]): 新的字典

    Returns:
        dict[str, Any]: 合并后的字典
    """
    for key, value in new.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            # 如果当前键对应的值是字典，则递归合并
            base[key] = merge_dicts(base[key], value)
        else:
            # 否则直接更新值
            base[key] = value
    return base
    
def flatten_dict(d: RawConfig, parent_key: str = '', sep: str = '.') -> RawConfig:
    """将嵌套字典扁平化

    Args:
        d (dict[str, Any]): 嵌套字典
        parent_key (str, optional): 父键名. 默认值为 ''
        sep (str, optional): 分隔符. 默认值为 '.'

    Returns:
        dict[str, Any]: 扁平化字典
        
    Example:
        input_dict = {
            "server": {
                "host": "localhost",
                "port: 8080
            }
        }
        
        output_dict = flatten_dict(input_dict)
        output_dict = {
            "server.host": "localhost",
            "server.port": 8080
        }
    """
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)

def load_from_dir(dir_path: str) -> RawConfig:
    """从目录中加载配置文件

    Args:
        dir_path (str): 目录路径
    """
    config: RawConfig = {}
    for file_name in os.listdir(dir_path):
        if file_name.endswith(".yaml") or file_name.endswith(".yml"):
            config = merge_dicts(config, load_from_yaml(os.path.join(dir_path, file_name)) or {})
        elif file_name.endswith(".json"):
            config = merge_dicts(config, load_from_json(os.path.join(dir_path, file_name)) or {})
        elif file_name.endswith(".toml"):
            config = merge_dicts(config, load_from_toml(os.path.join(dir_path, file_name)) or {})
            
    return config