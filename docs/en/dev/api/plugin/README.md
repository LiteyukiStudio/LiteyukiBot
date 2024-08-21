---
title: liteyuki.plugin
index: true
icon: laptop-code
category: API
---

### ***def*** `get_loaded_plugins() -> dict[str, Plugin]`

获取已加载的插件

Returns:

    dict[str, Plugin]: 插件字典

<details>
<summary>源代码</summary>

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

