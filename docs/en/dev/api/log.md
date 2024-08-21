---
title: liteyuki.log
order: 1
icon: laptop-code
category: API
---

### ***def*** `get_format(level: str) -> str`



<details>
<summary>源代码</summary>

```python
def get_format(level: str) -> str:
    if level == 'DEBUG':
        return debug_format
    else:
        return default_format
```
</details>

### ***def*** `init_log(config: dict) -> None`

在语言加载完成后执行

Returns:

<details>
<summary>源代码</summary>

```python
def init_log(config: dict):
    """
    在语言加载完成后执行
    Returns:

    """
    logger.remove()
    logger.add(sys.stdout, level=0, diagnose=False, format=get_format(config.get('log_level', 'INFO')))
    show_icon = config.get('log_icon', True)
    logger.level('DEBUG', color='<blue>', icon=f"{('🐛' if show_icon else '')}DEBUG")
    logger.level('INFO', color='<normal>', icon=f"{('ℹ️' if show_icon else '')}INFO")
    logger.level('SUCCESS', color='<green>', icon=f"{('✅' if show_icon else '')}SUCCESS")
    logger.level('WARNING', color='<yellow>', icon=f"{('⚠️' if show_icon else '')}WARNING")
    logger.level('ERROR', color='<red>', icon=f"{('⭕' if show_icon else '')}ERROR")
```
</details>

### ***var*** `logger = loguru.logger`



### ***var*** `show_icon = config.get('log_icon', True)`



