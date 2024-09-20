---
title: Process Communication
order: 4
---

# **Channel Communication**

### Introduction

LiteyukiBot is running in the main process MainProcess, and other plugin framework processes are child processes that come with it. 
Therefore, it is impossible to communicate through shared memory and direct object transfer. 
Liteyuki provides a channel [`Channel`](./api/comm/channel#class-channel-generic-t) for inter-process communication like `go`. 
You can send messages to other processes through [`Channel`](./api/comm/channel#class-channel-generic-t) and listen to messages from other processes.

### Example

The channel is full-duplex, with two receiving modes, but only one mode can be used for a channel, that is, passive mode and active mode, passive mode is implemented by the `chan.on_receive()` decorator callback function, and active mode needs to call `chan.receive()` to implement

- 创建子进程的同时会初始化一个被动通道和一个主动通道，且通道标识为`{process_name}-active`和`{process_name}-passive`，
- 主进程中通过`get_channel`函数获取通道对象
- 子进程中导入单例`active_channel`及`passive_channel`即可

> 在轻雪插件中(主进程中)

```python
import asyncio

from liteyuki.comm import get_channel, Channel
from liteyuki import get_bot

# get_channel函数获取通道对象，参数为调用set_channel时的通道标识
channel_passive = get_channel("nonebot-passive")  # 获取被动通道
channel_active = get_channel("nonebot-active")  # 获取主动通道
liteyuki_bot = get_bot()


# 注册一个函数在轻雪启动后运行
@liteyuki_bot.on_after_start
async def send_data():
    while True:
        channel_passive.send("I am liteyuki main process passive")
        channel_active.send("I am liteyuki main process active")
        await asyncio.sleep(3)  # 每3秒发送一次消息
```

> 在子进程中（例如NoneBot插件中）

```python
from nonebot import get_driver
from liteyuki.comm import active_channel, passive_channel  # 子进程中获取通道直接导入进程全局单例即可
from liteyuki.log import logger

driver = get_driver()


# 被动模式，通过装饰器注册一个函数在接收到消息时运行，每次接收到字符串数据时都会运行
@passive_channel.on_receive(filter_func=lambda data: isinstance(data, str))
async def on_passive_receive(data):
    logger.info(f"Passive receive: {data}")


# 注册一个函数在NoneBot启动后运行
@driver.on_startup
def on_startup():
    while True:
        data = active_channel.receive()
        logger.info(f"Active receive: {data}")
```

> 启动后控制台输出

```log
0000-00-00 00:00:00 [ℹ️信息] Passive receive: I am liteyuki main process passive
0000-00-00 00:00:00 [ℹ️信息] Active receive: I am liteyuki main process active
0000-00-00 00:00:03 [ℹ️信息] Passive receive: I am liteyuki main process passive
0000-00-00 00:00:03 [ℹ️信息] Active receive: I am liteyuki main process active
...
```

## **共享内存通信**

### 简介

- 相比于普通进程通信，内存共享使得代码编写更加简洁，轻雪框架提供了一个内存共享通信的接口，你可以通过`storage`模块实现内存共享通信，该模块封装通道实现
- 内存共享是线程安全的，你可以在多个线程中读写共享内存，线程锁会自动保护共享内存的读写操作

### 示例

> 在任意进程中均可使用

```python
from liteyuki.comm.storage import shared_memory

shared_memory.set("key", "value")  # 设置共享内存
value = shared_memory.get("key")  # 获取共享内存
```

源代码：[liteyuki/comm/storage.py](https://github.com/LiteyukiStudio/LiteyukiBot/blob/main/liteyuki/comm/storage.py)
