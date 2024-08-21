---
title: liteyuki.dev.plugin
order: 1
icon: laptop-code
category: API
---

### ***def*** `run_plugins() -> None`

运行插件，无需手动初始化bot

Args:

    module_path: 插件路径，参考`liteyuki.load_plugin`的函数签名

<details>
<summary>源代码</summary>

```python
def run_plugins(*module_path: str | Path):
    """
    运行插件，无需手动初始化bot
    Args:
        module_path: 插件路径，参考`liteyuki.load_plugin`的函数签名
    """
    cfg = load_config_in_default()
    plugins = cfg.get('liteyuki.plugins', [])
    plugins.extend(module_path)
    cfg['liteyuki.plugins'] = plugins
    bot = LiteyukiBot(**cfg)
    bot.run()
```
</details>

### ***var*** `cfg = load_config_in_default()`



### ***var*** `plugins = cfg.get('liteyuki.plugins', [])`



### ***var*** `bot = LiteyukiBot(**cfg)`



