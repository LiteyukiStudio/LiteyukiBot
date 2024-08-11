---
title: 进程通信
icon: exchange-alt
order: 4
category: 开发
---

## 简介

轻雪运行在主进程 MainProcess 里，其他插件框架进程是伴随的子进程，因此无法通过内存共享和直接对象传递的方式进行通信，轻雪提供了一个通道`Channel`用于跨进程通信，你可以通过`Channel`发送消息给其他进程，也可以监听其他进程的消息。

例如子进程接收到用户信息需要重启机器人，这时可以通过通道对主进程发送消息，主进程接收到消息后重启对应子进程。

## 快速开始

通道是全双工的，有两种接收模式，但一个通道只能使用一种，即被动模式和主动模式，被动模式由`chan.on_receive()`装饰回调函数实现，主动模式需调用`chan.receive()`实现

轻雪核心在创建子进程的同时会初始化两个通道，一个被动通道和一个主动通道，且通道标识为`{process_name}-active`和`{process_name}-passive`，你可以通过`get_channel`函数获取通道对象，然后通过`send`方法发送消息

- 在轻雪插件中

```python

import asyncio

from liteyuki.comm import get_channel, Channel
from liteyuki import get_bot

channel_passive = get_channel("nonebot-passive")
channel_active = get_channel("nonebot-active")
liteyuki_bot = get_bot()


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

channel_passive = get_channel("nonebot-passive")
channel_active = get_channel("nonebot-active")


@channel_passive.on_receive()
async def on_passive_receive(data):
    logger.info(f"Passive receive: {data}")


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