"""
---
title: liteyuki API
order: 100
---
此模块为liteyuki的框架整体

This module is the overall framework of liteyuki.
"""
from liteyuki.bot import (
    LiteyukiBot,
    get_bot,
    get_config,
    get_config_with_compat
)

from liteyuki.comm import (
    Channel,
    Event
)

from liteyuki.plugin import (
    load_plugin,
    load_plugins
)

from liteyuki.log import (
    init_log,
    logger
)

__all__ = [
        "LiteyukiBot",
        "get_bot",
        "get_config",
        "get_config_with_compat",
        "Channel",
        "Event",
        "load_plugin",
        "load_plugins",
        "init_log",
        "logger",
]

__version__ = "6.3.10"  # 测试版本号
# 6.3.10
# 新增`on_command`装饰器

# 6.3.9
# 更改了on语法

# 6.3.8
# 1. 初步添加对聊天的支持
# 2. 优化了通道的性能
