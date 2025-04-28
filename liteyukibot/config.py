from typing import Any

import json
import yaml
import tomllib

config: dict[str, Any] = {} # 全局配置map
flat_config: dict[str, Any] = {} # 扁平化配置map

def load_from_yaml(file_path: str) -> dict[str, Any]:
    """从yaml文件中加载配置并返回字典
    
    Args:
        file_path (str): yaml文件路径
    
    Returns:
        dict[str, Any]: 配置字典
    """
    with open(file_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)
    
def load_from_json(file_path: str) -> dict[str, Any]:
    """从json文件中加载配置并返回字典

    Args:
        file_path (str): json文件路径

    Returns:
        dict[str, Any]: 配置字典
    """
    
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)
    
def load_from_toml(file_path: str) -> dict[str, Any]:
    """从toml文件中加载配置并返回字典

    Args:
        file_path (str): toml文件路径

    Returns:
        dict[str, Any]: 配置字典
    """
    with open(file_path, "rb") as file:
        return tomllib.load(file)

def merge_to_config(new_config: dict[str, Any], warn: bool=True) -> None:
    """加载配置到全局配置字典，该函数有副作用，开发者尽量不要在多份配置文件中使用重复的配置项，否则会被覆盖

    Args:
        new_config (dict[str, Any]): 新的字典
        warn (bool, optional): 是否启用重复键警告. 默认 True.
    """
    global config, flat_config
    config.update(new_config)
    flat_config = flatten_dict(config)
    
def flatten_dict(d: dict[str, Any], parent_key: str = '', sep: str = '.') -> dict[str, Any]:
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

def load_config_to_global(reset: bool = False) -> None:
    """加载配置到全局配置字典

    Args:
        reset (bool, optional): 是否重置配置项. 默认 False.
    """
    