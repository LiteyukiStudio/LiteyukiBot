---
title: 内存共享通信
icon: exchange-alt
order: 5
category: 开发
---

# 简介

相比于普通进程通信，内存共享使得代码编写更加简洁，轻雪框架提供了一个内存共享通信的接口，你可以通过`shared_memory`模块实现内存共享通信
内存共享是线程安全的，你可以在多个线程中读写共享内存，线程锁会自动保护共享内存的读写操作

## 快速开始

- 在任意进程中均可使用

```python
from liteyuki.comm.storage import shared_memory

shared_memory.set("key", "value")  # 设置共享内存
value = shared_memory.get("key")  # 获取共享内存
```

- 源代码：[liteyuki/comm/storage.py](https://github.com/LiteyukiStudio/LiteyukiBot/blob/main/liteyuki/comm/storage.py)