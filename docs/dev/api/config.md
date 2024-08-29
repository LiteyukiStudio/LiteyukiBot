---
title: liteyuki.config
---
### *func* `flat_config() -> dict[str, Any]`



**说明**: 扁平化配置文件

{a:{b:{c:1}}} -> {"a.b.c": 1}

**参数**:
> - config: 配置项目  

**返回**: 扁平化后的配置文件，但也包含原有的键值对


<details>
<summary> <b>源代码</b> </summary>

```python
def flat_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    扁平化配置文件

    {a:{b:{c:1}}} -> {"a.b.c": 1}
    Args:
        config: 配置项目

    Returns:
        扁平化后的配置文件，但也包含原有的键值对
    """
    new_config = copy.deepcopy(config)
    for key, value in config.items():
        if isinstance(value, dict):
            for k, v in flat_config(value).items():
                new_config[f'{key}.{k}'] = v
    return new_config
```
</details>

### *func* `load_from_yaml() -> dict[str, Any]`



**说明**: Load config from yaml file


<details>
<summary> <b>源代码</b> </summary>

```python
def load_from_yaml(file_: str) -> dict[str, Any]:
    """
    Load config from yaml file

    """
    logger.debug(f'Loading YAML config from {file_}')
    config = yaml.safe_load(open(file_, 'r', encoding='utf-8'))
    return flat_config(config if config is not None else {})
```
</details>

### *func* `load_from_json() -> dict[str, Any]`



**说明**: Load config from json file


<details>
<summary> <b>源代码</b> </summary>

```python
def load_from_json(file_: str) -> dict[str, Any]:
    """
    Load config from json file
    """
    logger.debug(f'Loading JSON config from {file_}')
    config = json.load(open(file_, 'r', encoding='utf-8'))
    return flat_config(config if config is not None else {})
```
</details>

### *func* `load_from_toml() -> dict[str, Any]`



**说明**: Load config from toml file


<details>
<summary> <b>源代码</b> </summary>

```python
def load_from_toml(file_: str) -> dict[str, Any]:
    """
    Load config from toml file
    """
    logger.debug(f'Loading TOML config from {file_}')
    config = toml.load(open(file_, 'r', encoding='utf-8'))
    return flat_config(config if config is not None else {})
```
</details>

### *func* `load_from_files(*, no_warning: bool = False) -> dict[str, Any]`



**说明**: 从指定文件加载配置项，会自动识别文件格式
默认执行扁平化选项


<details>
<summary> <b>源代码</b> </summary>

```python
def load_from_files(*files: str, no_warning: bool=False) -> dict[str, Any]:
    """
    从指定文件加载配置项，会自动识别文件格式
    默认执行扁平化选项
    """
    config = {}
    for file in files:
        if os.path.exists(file):
            if file.endswith(('.yaml', 'yml')):
                config.update(load_from_yaml(file))
            elif file.endswith('.json'):
                config.update(load_from_json(file))
            elif file.endswith('.toml'):
                config.update(load_from_toml(file))
            elif not no_warning:
                logger.warning(f'Unsupported config file format: {file}')
        elif not no_warning:
            logger.warning(f'Config file not found: {file}')
    return config
```
</details>

### *func* `load_configs_from_dirs(*, no_waring: bool = False) -> dict[str, Any]`



**说明**: 从目录下加载配置文件，不递归
按照读取文件的优先级反向覆盖
默认执行扁平化选项


<details>
<summary> <b>源代码</b> </summary>

```python
def load_configs_from_dirs(*directories: str, no_waring: bool=False) -> dict[str, Any]:
    """
    从目录下加载配置文件，不递归
    按照读取文件的优先级反向覆盖
    默认执行扁平化选项
    """
    config = {}
    for directory in directories:
        if not os.path.exists(directory):
            if not no_waring:
                logger.warning(f'Directory not found: {directory}')
            continue
        for file in os.listdir(directory):
            if file.endswith(_SUPPORTED_CONFIG_FORMATS):
                config.update(load_from_files(os.path.join(directory, file), no_warning=no_waring))
    return config
```
</details>

### *func* `load_config_in_default(no_waring: bool = False) -> dict[str, Any]`



**说明**: 从一个标准的轻雪项目加载配置文件
项目目录下的config.*和config目录下的所有配置文件
项目目录下的配置文件优先


<details>
<summary> <b>源代码</b> </summary>

```python
def load_config_in_default(no_waring: bool=False) -> dict[str, Any]:
    """
    从一个标准的轻雪项目加载配置文件
    项目目录下的config.*和config目录下的所有配置文件
    项目目录下的配置文件优先
    """
    config = load_configs_from_dirs('config', no_waring=no_waring)
    config.update(load_from_files('config.yaml', 'config.toml', 'config.json', 'config.yml', no_warning=no_waring))
    return config
```
</details>

