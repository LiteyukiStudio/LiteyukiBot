import tempfile
from liteyukibot import config


def test_load_from_yaml():
    # 创建一个临时 YAML 文件内容
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
    json_content = '{"name": "LiteyukiBot", "version": "7.0.0"}'
    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as temp_file:
        temp_file.write(json_content)
        temp_file_path = temp_file.name

    result = config.load_from_json(temp_file_path)
    assert result["name"] == "LiteyukiBot"
    assert result["version"] == "7.0.0"


def test_load_from_toml():
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