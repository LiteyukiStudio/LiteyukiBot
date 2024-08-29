---
title: liteyuki.core.manager
---
### **class** `ChannelDeliver`
### *method* `__init__(self, active: Channel[Any], passive: Channel[Any], channel_deliver_active: Channel[Channel[Any]], channel_deliver_passive: Channel[tuple[str, dict]], publish: Channel[tuple[str, Any]])`


<details>
<summary> <b>Source code</b> </summary>

```python
def __init__(self, active: Channel[Any], passive: Channel[Any], channel_deliver_active: Channel[Channel[Any]], channel_deliver_passive: Channel[tuple[str, dict]], publish: Channel[tuple[str, Any]]):
    self.active = active
    self.passive = passive
    self.channel_deliver_active = channel_deliver_active
    self.channel_deliver_passive = channel_deliver_passive
    self.publish = publish
```
</details>

### **class** `ProcessManager`
### *method* `__init__(self, lifespan: Lifespan)`


<details>
<summary> <b>Source code</b> </summary>

```python
def __init__(self, lifespan: 'Lifespan'):
    self.lifespan = lifespan
    self.targets: dict[str, tuple[Callable, tuple, dict]] = {}
    self.processes: dict[str, Process] = {}
```
</details>

### *method* `start(self, name: str)`



**Description**: 开启后自动监控进程，并添加到进程字典中

**Arguments**:
> - name:   


<details>
<summary> <b>Source code</b> </summary>

```python
def start(self, name: str):
    """
        开启后自动监控进程，并添加到进程字典中
        Args:
            name:
        Returns:

        """
    if name not in self.targets:
        raise KeyError(f'Process {name} not found.')
    chan_active = get_channel(f'{name}-active')

    def _start_process():
        process = Process(target=self.targets[name][0], args=self.targets[name][1], kwargs=self.targets[name][2], daemon=True)
        self.processes[name] = process
        process.start()
    _start_process()
    while True:
        data = chan_active.receive()
        if data == 0:
            logger.info(f'Stopping process {name}')
            self.lifespan.before_process_shutdown()
            self.terminate(name)
            break
        elif data == 1:
            logger.info(f'Restarting process {name}')
            self.lifespan.before_process_shutdown()
            self.lifespan.before_process_restart()
            self.terminate(name)
            _start_process()
            continue
        else:
            logger.warning('Unknown data received, ignored.')
```
</details>

### *method* `start_all(self)`



**Description**: 启动所有进程


<details>
<summary> <b>Source code</b> </summary>

```python
def start_all(self):
    """
        启动所有进程
        """
    for name in self.targets:
        threading.Thread(target=self.start, args=(name,), daemon=True).start()
```
</details>

### *method* `add_target(self, name: str, target: TARGET_FUNC, args: tuple = (), kwargs = None)`



**Description**: 添加进程

**Arguments**:
> - name: 进程名，用于获取和唯一标识  
> - target: 进程函数  
> - args: 进程函数参数  
> - kwargs: 进程函数关键字参数，通常会默认传入chan_active和chan_passive  


<details>
<summary> <b>Source code</b> </summary>

```python
def add_target(self, name: str, target: TARGET_FUNC, args: tuple=(), kwargs=None):
    """
        添加进程
        Args:
            name: 进程名，用于获取和唯一标识
            target: 进程函数
            args: 进程函数参数
            kwargs: 进程函数关键字参数，通常会默认传入chan_active和chan_passive
        """
    if kwargs is None:
        kwargs = {}
    chan_active: Channel = Channel(_id=f'{name}-active')
    chan_passive: Channel = Channel(_id=f'{name}-passive')
    channel_deliver = ChannelDeliver(active=chan_active, passive=chan_passive, channel_deliver_active=channel_deliver_active_channel, channel_deliver_passive=channel_deliver_passive_channel, publish=publish_channel)
    self.targets[name] = (_delivery_channel_wrapper, (target, channel_deliver, shared_memory, *args), kwargs)
    set_channels({f'{name}-active': chan_active, f'{name}-passive': chan_passive})
```
</details>

### *method* `join_all(self)`


<details>
<summary> <b>Source code</b> </summary>

```python
def join_all(self):
    for name, process in self.targets:
        process.join()
```
</details>

### *method* `terminate(self, name: str)`



**Description**: 终止进程并从进程字典中删除

**Arguments**:
> - name:   


<details>
<summary> <b>Source code</b> </summary>

```python
def terminate(self, name: str):
    """
        终止进程并从进程字典中删除
        Args:
            name:

        Returns:

        """
    if name not in self.processes:
        logger.warning(f'Process {name} not found.')
        return
    process = self.processes[name]
    process.terminate()
    process.join(TIMEOUT)
    if process.is_alive():
        process.kill()
    logger.success(f'Process {name} terminated.')
```
</details>

### *method* `terminate_all(self)`


<details>
<summary> <b>Source code</b> </summary>

```python
def terminate_all(self):
    for name in self.targets:
        self.terminate(name)
```
</details>

### *method* `is_process_alive(self, name: str) -> bool`



**Description**: 检查进程是否存活

**Arguments**:
> - name:   


<details>
<summary> <b>Source code</b> </summary>

```python
def is_process_alive(self, name: str) -> bool:
    """
        检查进程是否存活
        Args:
            name:

        Returns:

        """
    if name not in self.targets:
        logger.warning(f'Process {name} not found.')
    return self.processes[name].is_alive()
```
</details>

### ***var*** `TARGET_FUNC = Callable[..., Any]`

- **Type**: `TypeAlias`

