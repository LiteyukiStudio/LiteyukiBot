---
title: liteyuki.plugins.plugin_loader
---
### *func* `default_plugins_loader()`



**Description**: 默认插件加载器，应在初始化时调用


<details>
<summary> <b>Source code</b> </summary>

```python
def default_plugins_loader():
    """
    默认插件加载器，应在初始化时调用
    """
    for plugin in get_config('liteyuki.plugins', []):
        load_plugin(plugin)
    for plugin_dir in get_config('liteyuki.plugin_dirs', ['src/liteyuki_plugins']):
        load_plugins(plugin_dir)
```
</details>

