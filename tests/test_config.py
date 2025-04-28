import tempfile

from liteyukibot import config
from pydantic import BaseModel, Field


class ConfigModel(BaseModel):
    name: str
    version: int
    server_host: str = Field(alias="server.host")
    server_port: int = Field(alias="server.port")
    


def test_load_from_yaml():
    """测试从yaml文件路径加载配置项"""
    yaml_content = """
    name: LiteyukiBot
    version: 7.0.0
    """
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as temp_file:
        temp_file.write(yaml_content)
        temp_file_path = temp_file.name

    result = config.load_from_yaml(temp_file_path)
    assert result["name"] == "LiteyukiBot"
    assert result["version"] == "7.0.0"


def test_load_from_json():
    """测试从json文件路径加载配置"""
    json_content = '{"name": "LiteyukiBot", "version": "7.0.0"}'
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as temp_file:
        temp_file.write(json_content)
        temp_file_path = temp_file.name

    result = config.load_from_json(temp_file_path)
    assert result["name"] == "LiteyukiBot"
    assert result["version"] == "7.0.0"


def test_load_from_toml():
    """测试从toml文件路径加载配置"""
    toml_content = """
    [info]
    name = "LiteyukiBot"
    version = "7.0.0"
    """
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".toml") as temp_file:
        temp_file.write(toml_content)
        temp_file_path = temp_file.name

    result = config.load_from_toml(temp_file_path)
    assert result["info"]["name"] == "LiteyukiBot"
    assert result["info"]["version"] == "7.0.0"
    
    
def test_flatten_dict():
    """测试扁平化字典"""
    nested_dict = {
        "name": "LiteyukiBot",
        "version": {
            "major": 7,
            "minor": 0,
            "patch": 0
        },
        "server": {
            "db": {
                "host": "localhost",
                "port": 8080
            },
            "tags": ["tag1", "tag2"]
        }
    }
    flat_dict = config.flatten_dict(nested_dict)
    assert flat_dict["name"] == "LiteyukiBot"
    assert flat_dict["version.major"] == 7
    assert flat_dict["version.minor"] == 0
    assert flat_dict["version.patch"] == 0
    assert flat_dict["server.db.host"] == "localhost"
    assert flat_dict["server.db.port"] == 8080
    assert flat_dict["server.tags"] == ["tag1", "tag2"]
    
def test_merge_to_config():
    """测试合并配置"""
    old_config = {
        "name": "LiteyukiBot",
        "version": 7,
        "server": {
            "host": "localhost",
            "port": 8080
        }
    }
    config.merge_to_config(old_config)
    assert config.config["name"] == "LiteyukiBot"
    new_config = {
        "version": 8,
        "server": {
            "port": 9090
        },
        "new_key": "new_value"
    }
    
    config.merge_to_config(new_config)
    
    # config
    assert config.config["name"] == "LiteyukiBot"
    assert config.config["version"] == 8
    assert config.config["server"]["host"] == "localhost"
    assert config.config["server"]["port"] == 9090
    assert config.config["new_key"] == "new_value"
    # test flatten_config
    assert config.flat_config["name"] == "LiteyukiBot"
    assert config.flat_config["version"] == 8
    assert config.flat_config["server.host"] == "localhost"
    assert config.flat_config["server.port"] == 9090
    assert config.flat_config["new_key"] == "new_value"
    
def test_get_config():
    """测试获取配置项"""
    config_data = {
        "name": "LiteyukiBot",
        "version": 7,
        "server": {
            "host": "localhost",
            "port": 8080
        }
    }
    config.merge_to_config(config_data)
    assert config.get("name") == "LiteyukiBot"
    assert config.get("version") == 7
    assert config.get("server.host") == "localhost"
    assert config.get("server.port") == 8080
    assert config.get("non_existent_key", default="default_value") == "default_value"
    assert config.get("non_existent_key", default=42) == 42
    
    
def test_bind():
    """测试配置项绑定到模型"""
    config_data = {
        "name": "LiteyukiBot",
        "version": 7,
        "server": {
            "host": "localhost",
            "port": 8080
        }
    }
    config.merge_to_config(config_data)
    bound_model = config.bind(ConfigModel)
    assert bound_model.name == "LiteyukiBot"
    assert bound_model.version == 7
    assert bound_model.server_host == "localhost"
    assert bound_model.server_port == 8080