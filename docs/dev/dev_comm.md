---
title: 进程通信
icon: exchange-alt
order: 4
category: 开发
---

## **通道通信**

### 简介

轻雪运行在主进程 MainProcess 里，其他插件框架进程是伴随的子进程，因此无法通过内存共享和直接对象传递的方式进行通信，轻雪提供了一个通道`Channel`用于跨进程通信，你可以通过`Channel`发送消息给其他进程，也可以监听其他进程的消息。

例如子进程接收到用户信息需要重启机器人，这时可以通过通道对主进程发送消息，主进程接收到消息后重启对应子进程。

### 快速开始

通道是全双工的，有两种接收模式，但一个通道只能使用一种，即被动模式和主动模式，被动模式由`chan.on_receive()`装饰回调函数实现，主动模式需调用`chan.receive()`实现

轻雪核心在创建子进程的同时会初始化两个通道，一个被动通道和一个主动通道，且通道标识为`{process_name}-active`和`{process_name}-passive`，你可以通过`get_channel`函数获取通道对象，然后通过`send`方法发送消息

- 在轻雪插件中

```python

import asyncio

from liteyuki.comm import get_channel, Channel
from liteyuki import get_bot
# get_channel函数获取通道对象，参数为调用set_channel时的通道标识
# 每个进程只能获取在当前进程通过set_channel设置的通道
# 轻雪已经在创建进程时把每个通道都传递给了主进程和子进程，以便在哪个进程都可以被获取
channel_passive = get_channel("nonebot-passive")    # 获取被动通道
channel_active = get_channel("nonebot-active")  # 获取主动通道
liteyuki_bot = get_bot()

# 注册一个函数在轻雪启动后运行
@liteyuki_bot.on_after_start
async def do_something_after_start():
    while True:
        channel_passive.send("I am liteyuki main process passive")
        await asyncio.sleep(0.1)
        channel_active.send("I am liteyuki main process active")
        await asyncio.sleep(3)
```

- 在子进程中（可以是NoneBot插件中）

```python
from nonebot import get_driver
from liteyuki.comm import get_channel
from liteyuki.log import logger

driver = get_driver()

# 通过get_channel函数获取通道对象，参数为调用set_channel时的通道标识
channel_passive = get_channel("nonebot-passive")
channel_active = get_channel("nonebot-active")

# 被动模式，通过装饰器注册一个函数在接收到消息时运行，每次接收到字符串数据时都会运行
@channel_passive.on_receive(filter_func=lambda data: isinstance(data, str))
async def on_passive_receive(data):
    logger.info(f"Passive receive: {data}")

    
# 注册一个函数在NoneBot启动后运行
@driver.on_startup
async def on_startup():
    while True:
        data = channel_active.receive()
        logger.info(f"Active receive: {data}")
```

- 启动后控制台输出

```shell
..-..-.. ..:..:.. [ℹ️信息] Passive receive: I am liteyuki main process passive
..-..-.. ..:..:.. [ℹ️信息] Active receive: I am liteyuki main process active
..-..-.. ..:..:.. [ℹ️信息] Passive receive: I am liteyuki main process passive
..-..-.. ..:..:.. [ℹ️信息] Active receive: I am liteyuki main process active
...
```

## **共享内存通信**

### 简介

- 相比于普通进程通信，内存共享使得代码编写更加简洁，轻雪框架提供了一个内存共享通信的接口，你可以通过`storage`模块实现内存共享通信
- 内存共享是线程安全的，你可以在多个线程中读写共享内存，线程锁会自动保护共享内存的读写操作

### 快速开始

- 在任意进程中均可使用

```python
from liteyuki.comm.storage import shared_memory

shared_memory.set("key", "value")  # 设置共享内存
value = shared_memory.get("key")  # 获取共享内存
```

- 源代码：[liteyuki/comm/storage.py](https://github.com/LiteyukiStudio/LiteyukiBot/blob/main/liteyuki/comm/storage.py)