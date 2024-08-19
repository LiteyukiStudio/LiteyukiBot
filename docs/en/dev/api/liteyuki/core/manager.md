---
title: liteyuki.core.manager
order: 1
icon: laptop-code
category: API
---

### ***class*** `ChannelDeliver`



### ***class*** `ProcessManager`

进程管理器

### &emsp; ***def*** `start(self: Any, name: str) -> None`

&emsp;开启后自动监控进程，并添加到进程字典中

Args:

    name:

Returns:

### &emsp; ***def*** `start_all(self: Any) -> None`

&emsp;启动所有进程

### &emsp; ***def*** `add_target(self: Any, name: str, target: TARGET_FUNC, args: tuple, kwargs: Any) -> None`

&emsp;添加进程

Args:

    name: 进程名，用于获取和唯一标识

    target: 进程函数

    args: 进程函数参数

    kwargs: 进程函数关键字参数，通常会默认传入chan_active和chan_passive

### &emsp; ***def*** `join_all(self: Any) -> None`

&emsp;

### &emsp; ***def*** `terminate(self: Any, name: str) -> None`

&emsp;终止进程并从进程字典中删除

Args:

    name:



Returns:

### &emsp; ***def*** `terminate_all(self: Any) -> None`

&emsp;

### &emsp; ***def*** `is_process_alive(self: Any, name: str) -> bool`

&emsp;检查进程是否存活

Args:

    name:



Returns:

