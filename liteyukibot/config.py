
from typing import Any

import json
import yaml
import tomllib


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