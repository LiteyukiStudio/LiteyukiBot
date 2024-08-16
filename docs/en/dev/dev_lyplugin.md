---
title: Liteyuki Plugin
icon: laptop-code
order: 3
category: development
---


## 简介

轻雪插件是轻雪内置的一部分功能，运行在主进程中，可以很高程度地扩展轻雪的功能

## 开始

### 创建插件

在标准项目中，位于liteyuki/plugins和src/liteyuki_plugins下的Python modules均会被当作插件加载，你可自行添加配置文件以指定插件的加载路径
一个`.py`文件或一个包含`__init__.py`的文件夹即可被识别为插件
创建一个文件夹，例如`watchdog_plugin`，并在其中创建一个`__init__.py`文件，即可创建一个插件

```python
from liteyuki.plugin import PluginMetadata

# 定义插件元数据，推荐填写
__plugin_meta__ = PluginMetadata(
    name="NoneDog",       # 插件名称
    version="1.0.0",        # 插件版本
    description="A simple plugin for nonebot developer"   # 插件描述
)

# 你的插件代码
...
```

### 编写逻辑部分

轻雪主进程不涉及聊天部分，因此插件主要是一些后台任务或者与聊天机器人的通信
以下我们会编写一个简单的插件，用于开发NoneBot时进行文件系统变更重载

```python
import os
from liteyuki.dev import observer   # 导入文件系统观察器
from liteyuki import get_bot, logger    # 导入轻雪Bot和日志
from watchdog.events import FileSystemEvent   # 导入文件系统事件

liteyuki = get_bot()    # 获取唯一的轻雪Bot实例

exclude_extensions = (".pyc", ".pyo")   # 排除的文件扩展名


# 用observer的on_file_system_event装饰器监听文件系统事件
@observer.on_file_system_event(
    directories=("src/nonebot_plugins",),
    event_filter=lambda event: not event.src_path.endswith(exclude_extensions) and ("__pycache__" not in event.src_path) and os.path.isfile(event.src_path)
)
def restart_nonebot_process(event: FileSystemEvent):
    logger.debug(f"File {event.src_path} changed, reloading nonebot...")
    liteyuki.restart_process("nonebot") # 调用重启进程方法
```

### 加载插件

在配置文件中的`liteyuki.plugins`中添加你的插件路径，例如`watchdog_plugin`，重启轻雪即可加载插件。然后我们在src/nonebot_plugins下创建一个文件，例如`test.py`，并在其中写入一些代码，保存后轻雪会自动重载NoneBot进程