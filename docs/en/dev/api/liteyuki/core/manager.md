---
title: liteyuki.core.manager
order: 1
icon: laptop-code
category: API
---

### ***class*** `ChannelDeliver`



### &emsp; ***def*** `__init__(self, active: Channel[Any], passive: Channel[Any], channel_deliver_active: Channel[Channel[Any]], channel_deliver_passive: Channel[tuple[str, dict]]) -> None`

&emsp;

### ***class*** `ProcessManager`

进程管理器

### &emsp; ***def*** `__init__(self, lifespan: 'Lifespan') -> None`

&emsp;

### &emsp; ***def*** `start(self, name: str) -> None`

&emsp;开启后自动监控进程，并添加到进程字典中

Args:

    name:

Returns:

### &emsp; ***def*** `start_all(self) -> None`

&emsp;启动所有进程

### &emsp; ***def*** `add_target(self, name: str, target: TARGET_FUNC, args: tuple, kwargs: Any) -> None`

&emsp;添加进程

Args:

    name: 进程名，用于获取和唯一标识

    target: 进程函数

    args: 进程函数参数

    kwargs: 进程函数关键字参数，通常会默认传入chan_active和chan_passive

### &emsp; ***def*** `join_all(self) -> None`

&emsp;

### &emsp; ***def*** `terminate(self, name: str) -> None`

&emsp;终止进程并从进程字典中删除

Args:

    name:



Returns:

### &emsp; ***def*** `terminate_all(self) -> None`

&emsp;

### &emsp; ***def*** `is_process_alive(self, name: str) -> bool`

&emsp;检查进程是否存活

Args:

    name:



Returns:

### ***var*** `TIMEOUT = 10`



### ***var*** `chan_active = get_channel(f'{name}-active')`



### ***var*** `channel_deliver = ChannelDeliver(active=chan_active, passive=chan_passive, channel_deliver_active=channel_deliver_active_channel, channel_deliver_passive=channel_deliver_passive_channel)`



### ***var*** `process = self.processes[name]`



### ***var*** `process = Process(target=self.targets[name][0], args=self.targets[name][1], kwargs=self.targets[name][2], daemon=True)`



### ***var*** `data = chan_active.receive()`



### ***var*** `kwargs = {}`



