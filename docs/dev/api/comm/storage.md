---
title: liteyuki.comm.storage
---
### `@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get')`
### *func* `on_get()`


<details>
<summary> <b>源代码</b> </summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get')
def on_get(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    default = data[1]['default']
    recv_chan = data[1]['recv_chan']
    recv_chan.send(shared_memory.get(key, default))
```
</details>

### `@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'set')`
### *func* `on_set()`


<details>
<summary> <b>源代码</b> </summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'set')
def on_set(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    value = data[1]['value']
    shared_memory.set(key, value)
```
</details>

### `@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'delete')`
### *func* `on_delete()`


<details>
<summary> <b>源代码</b> </summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'delete')
def on_delete(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    shared_memory.delete(key)
```
</details>

### `@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get_all')`
### *func* `on_get_all()`


<details>
<summary> <b>源代码</b> </summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get_all')
def on_get_all(data: tuple[str, dict[str, Any]]):
    recv_chan = data[1]['recv_chan']
    recv_chan.send(shared_memory.get_all())
```
</details>

### `@channel.publish_channel.on_receive()`
### *func* `on_publish()`


<details>
<summary> <b>源代码</b> </summary>

```python
@channel.publish_channel.on_receive()
def on_publish(data: tuple[str, Any]):
    channel_, data = data
    shared_memory.run_subscriber_receive_funcs(channel_, data)
```
</details>

### **class** `Subscriber`
### *method* `__init__(self)`


<details>
<summary> <b>源代码</b> </summary>

```python
def __init__(self):
    self._subscribers = {}
```
</details>

### *method* `receive(self) -> Any`


<details>
<summary> <b>源代码</b> </summary>

```python
def receive(self) -> Any:
    pass
```
</details>

### *method* `unsubscribe(self) -> None`


<details>
<summary> <b>源代码</b> </summary>

```python
def unsubscribe(self) -> None:
    pass
```
</details>

### **class** `KeyValueStore`
### *method* `__init__(self)`


<details>
<summary> <b>源代码</b> </summary>

```python
def __init__(self):
    self._store = {}
    self.active_chan = Channel[tuple[str, Optional[dict[str, Any]]]](_id='shared_memory-active')
    self.passive_chan = Channel[tuple[str, Optional[dict[str, Any]]]](_id='shared_memory-passive')
    self.publish_channel = Channel[tuple[str, Any]](_id='shared_memory-publish')
    self.is_main_receive_loop_running = False
    self.is_sub_receive_loop_running = False
```
</details>

### *method* `set(self, key: str, value: Any) -> None`



**说明**: 设置键值对

**参数**:
> - key: 键  
> - value: 值  


<details>
<summary> <b>源代码</b> </summary>

```python
def set(self, key: str, value: Any) -> None:
    """
        设置键值对
        Args:
            key: 键
            value: 值

        """
    if IS_MAIN_PROCESS:
        lock = _get_lock(key)
        with lock:
            self._store[key] = value
    else:
        self.passive_chan.send(('set', {'key': key, 'value': value}))
```
</details>

### *method* `get(self, key: str, default: Optional[Any] = None) -> Optional[Any]`



**说明**: 获取键值对

**参数**:
> - key: 键  
> - default: 默认值  

**返回**: Any: 值


<details>
<summary> <b>源代码</b> </summary>

```python
def get(self, key: str, default: Optional[Any]=None) -> Optional[Any]:
    """
        获取键值对
        Args:
            key: 键
            default: 默认值

        Returns:
            Any: 值
        """
    if IS_MAIN_PROCESS:
        lock = _get_lock(key)
        with lock:
            return self._store.get(key, default)
    else:
        recv_chan = Channel[Optional[Any]]('recv_chan')
        self.passive_chan.send(('get', {'key': key, 'default': default, 'recv_chan': recv_chan}))
        return recv_chan.receive()
```
</details>

### *method* `delete(self, key: str, ignore_key_error: bool = True) -> None`



**说明**: 删除键值对

**参数**:
> - key: 键  
> - ignore_key_error: 是否忽略键不存在的错误  


<details>
<summary> <b>源代码</b> </summary>

```python
def delete(self, key: str, ignore_key_error: bool=True) -> None:
    """
        删除键值对
        Args:
            key: 键
            ignore_key_error: 是否忽略键不存在的错误

        Returns:
        """
    if IS_MAIN_PROCESS:
        lock = _get_lock(key)
        with lock:
            if key in self._store:
                try:
                    del self._store[key]
                    del _locks[key]
                except KeyError as e:
                    if not ignore_key_error:
                        raise e
    else:
        self.passive_chan.send(('delete', {'key': key}))
```
</details>

### *method* `get_all(self) -> dict[str, Any]`



**说明**: 获取所有键值对

**返回**: dict[str, Any]: 键值对


<details>
<summary> <b>源代码</b> </summary>

```python
def get_all(self) -> dict[str, Any]:
    """
        获取所有键值对
        Returns:
            dict[str, Any]: 键值对
        """
    if IS_MAIN_PROCESS:
        return self._store
    else:
        recv_chan = Channel[dict[str, Any]]('recv_chan')
        self.passive_chan.send(('get_all', {'recv_chan': recv_chan}))
        return recv_chan.receive()
```
</details>

### *method* `publish(self, channel_: str, data: Any) -> None`



**说明**: 发布消息

**参数**:
> - channel_: 频道  
> - data: 数据  


<details>
<summary> <b>源代码</b> </summary>

```python
def publish(self, channel_: str, data: Any) -> None:
    """
        发布消息
        Args:
            channel_: 频道
            data: 数据

        Returns:
        """
    self.active_chan.send(('publish', {'channel': channel_, 'data': data}))
```
</details>

### *method* `on_subscriber_receive(self, channel_: str) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]`



**说明**: 订阅者接收消息时的回调

**参数**:
> - channel_: 频道  

**返回**: 装饰器


<details>
<summary> <b>源代码</b> </summary>

```python
def on_subscriber_receive(self, channel_: str) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]:
    """
        订阅者接收消息时的回调
        Args:
            channel_: 频道

        Returns:
            装饰器
        """
    if IS_MAIN_PROCESS and (not self.is_main_receive_loop_running):
        threading.Thread(target=self._start_receive_loop, daemon=True).start()
        shared_memory.is_main_receive_loop_running = True
    elif not IS_MAIN_PROCESS and (not self.is_sub_receive_loop_running):
        threading.Thread(target=self._start_receive_loop, daemon=True).start()
        shared_memory.is_sub_receive_loop_running = True

    def decorator(func: ON_RECEIVE_FUNC) -> ON_RECEIVE_FUNC:

        async def wrapper(data: Any):
            if is_coroutine_callable(func):
                await func(data)
            else:
                func(data)
        if IS_MAIN_PROCESS:
            if channel_ not in _on_main_subscriber_receive_funcs:
                _on_main_subscriber_receive_funcs[channel_] = []
            _on_main_subscriber_receive_funcs[channel_].append(wrapper)
        else:
            if channel_ not in _on_sub_subscriber_receive_funcs:
                _on_sub_subscriber_receive_funcs[channel_] = []
            _on_sub_subscriber_receive_funcs[channel_].append(wrapper)
        return wrapper
    return decorator
```
</details>

### `@staticmethod`
### *method* `run_subscriber_receive_funcs(channel_: str, data: Any)`



**说明**: 运行订阅者接收函数

**参数**:
> - channel_: 频道  
> - data: 数据  


<details>
<summary> <b>源代码</b> </summary>

```python
@staticmethod
def run_subscriber_receive_funcs(channel_: str, data: Any):
    """
        运行订阅者接收函数
        Args:
            channel_: 频道
            data: 数据
        """
    if IS_MAIN_PROCESS:
        if channel_ in _on_main_subscriber_receive_funcs and _on_main_subscriber_receive_funcs[channel_]:
            run_coroutine_in_thread(*[func(data) for func in _on_main_subscriber_receive_funcs[channel_]])
    elif channel_ in _on_sub_subscriber_receive_funcs and _on_sub_subscriber_receive_funcs[channel_]:
        run_coroutine_in_thread(*[func(data) for func in _on_sub_subscriber_receive_funcs[channel_]])
```
</details>

### *method* `_start_receive_loop(self)`



**说明**: 启动发布订阅接收器循环，在主进程中运行，若有子进程订阅则推送给子进程


<details>
<summary> <b>源代码</b> </summary>

```python
def _start_receive_loop(self):
    """
        启动发布订阅接收器循环，在主进程中运行，若有子进程订阅则推送给子进程
        """
    if IS_MAIN_PROCESS:
        while True:
            data = self.active_chan.receive()
            if data[0] == 'publish':
                self.run_subscriber_receive_funcs(data[1]['channel'], data[1]['data'])
                self.publish_channel.send(data)
    else:
        while True:
            data = self.publish_channel.receive()
            if data[0] == 'publish':
                self.run_subscriber_receive_funcs(data[1]['channel'], data[1]['data'])
```
</details>

### **class** `GlobalKeyValueStore`
### `@classmethod`
### *method* `get_instance(cls)`


<details>
<summary> <b>源代码</b> </summary>

```python
@classmethod
def get_instance(cls):
    if cls._instance is None:
        with cls._lock:
            if cls._instance is None:
                cls._instance = KeyValueStore()
    return cls._instance
```
</details>

### ***var*** `_on_main_subscriber_receive_funcs = {}`

- **类型**: `dict[str, list[ASYNC_ON_RECEIVE_FUNC]]`

- **说明**: 主进程订阅者接收函数

### ***var*** `_on_sub_subscriber_receive_funcs = {}`

- **类型**: `dict[str, list[ASYNC_ON_RECEIVE_FUNC]]`

- **说明**: 子进程订阅者接收函数

### ***var*** `shared_memory = GlobalKeyValueStore.get_instance()`

- **类型**: `KeyValueStore`

