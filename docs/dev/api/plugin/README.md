---
title: liteyuki.plugin
---
### *func* `get_loaded_plugins() -> dict[str, Plugin]`



**说明**: 获取已加载的插件

**返回**: dict[str, Plugin]: 插件字典


<details>
<summary> <b>源代码</b> </summary>

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

