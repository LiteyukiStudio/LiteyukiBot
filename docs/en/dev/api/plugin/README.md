---
title: liteyuki.plugin
---
### *func* `get_loaded_plugins() -> dict[str, Plugin]`



**Description**: 获取已加载的插件

**Return**: dict[str, Plugin]: 插件字典


<details>
<summary> <b>Source code</b> </summary>

```python
def get_loaded_plugins() -> dict[str, Plugin]:
    """
    获取已加载的插件
    Returns:
        dict[str, Plugin]: 插件字典
    """
    return _plugins
```
</details>

