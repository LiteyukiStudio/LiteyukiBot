---
title: liteyuki.config
order: 1
icon: laptop-code
category: API
---

### ***def*** `flat_config(config: dict[str, Any]) -> dict[str, Any]`

扁平化配置文件

{a:{b:{c:1}}} -> {"a.b.c": 1}
Args:
    config: 配置项目

Returns:
    扁平化后的配置文件，但也包含原有的键值对

### ***def*** `load_from_yaml(file: str) -> dict[str, Any]`

Load config from yaml file

### ***def*** `load_from_json(file: str) -> dict[str, Any]`

Load config from json file

### ***def*** `load_from_toml(file: str) -> dict[str, Any]`

Load config from toml file

### ***def*** `load_from_files() -> dict[str, Any]`

从指定文件加载配置项，会自动识别文件格式
默认执行扁平化选项

### ***def*** `load_configs_from_dirs() -> dict[str, Any]`

从目录下加载配置文件，不递归
按照读取文件的优先级反向覆盖
默认执行扁平化选项

### ***def*** `load_config_in_default(no_waring: bool) -> dict[str, Any]`

从一个标准的轻雪项目加载配置文件
项目目录下的config.*和config目录下的所有配置文件
项目目录下的配置文件优先

### ***class*** `SatoriNodeConfig(BaseModel)`



### ***class*** `SatoriConfig(BaseModel)`



### ***class*** `BasicConfig(BaseModel)`



