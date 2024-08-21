---
title: liteyuki.comm.storage
order: 1
icon: laptop-code
category: API
---

### ***def*** `run_subscriber_receive_funcs(channel_: str, data: Any) -> None`

运行订阅者接收函数

Args:

    channel_: 频道

    data: 数据

<details>
<summary>源代码</summary>

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
            run_coroutine(*[func(data) for func in _on_main_subscriber_receive_funcs[channel_]])
    elif channel_ in _on_sub_subscriber_receive_funcs and _on_sub_subscriber_receive_funcs[channel_]:
        run_coroutine(*[func(data) for func in _on_sub_subscriber_receive_funcs[channel_]])
```
</details>

### ***def*** `on_get(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get')
def on_get(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    default = data[1]['default']
    recv_chan = data[1]['recv_chan']
    recv_chan.send(shared_memory.get(key, default))
```
</details>

### ***def*** `on_set(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'set')
def on_set(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    value = data[1]['value']
    shared_memory.set(key, value)
```
</details>

### ***def*** `on_delete(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'delete')
def on_delete(data: tuple[str, dict[str, Any]]):
    key = data[1]['key']
    shared_memory.delete(key)
```
</details>

### ***def*** `on_get_all(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@shared_memory.passive_chan.on_receive(lambda d: d[0] == 'get_all')
def on_get_all(data: tuple[str, dict[str, Any]]):
    recv_chan = data[1]['recv_chan']
    recv_chan.send(shared_memory.get_all())
```
</details>

### ***def*** `on_publish(data: tuple[str, Any]) -> None`



<details>
<summary>源代码</summary>

```python
@channel.publish_channel.on_receive()
def on_publish(data: tuple[str, Any]):
    channel_, data = data
    shared_memory.run_subscriber_receive_funcs(channel_, data)
```
</details>

### ***def*** `decorator(func: ON_RECEIVE_FUNC) -> ON_RECEIVE_FUNC`



<details>
<summary>源代码</summary>

```python
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
```
</details>

### ***async def*** `wrapper(data: Any) -> None`



<details>
<summary>源代码</summary>

```python
async def wrapper(data: Any):
    if is_coroutine_callable(func):
        await func(data)
    else:
        func(data)
```
</details>

### ***class*** `Subscriber`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def __init__(self):
    self._subscribers = {}
```
</details>

### &emsp; ***def*** `receive(self) -> Any`

&emsp;

<details>
<summary>源代码</summary>

```python
def receive(self) -> Any:
    pass
```
</details>

### &emsp; ***def*** `unsubscribe(self) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def unsubscribe(self) -> None:
    pass
```
</details>

### ***class*** `KeyValueStore`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `set(self, key: str, value: Any) -> None`

&emsp;设置键值对

Args:

    key: 键

    value: 值

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `get(self, key: str, default: Optional[Any]) -> Optional[Any]`

&emsp;获取键值对

Args:

    key: 键

    default: 默认值



Returns:

    Any: 值

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `delete(self, key: str, ignore_key_error: bool) -> None`

&emsp;删除键值对

Args:

    key: 键

    ignore_key_error: 是否忽略键不存在的错误



Returns:

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `get_all(self) -> dict[str, Any]`

&emsp;获取所有键值对

Returns:

    dict[str, Any]: 键值对

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `publish(self, channel_: str, data: Any) -> None`

&emsp;发布消息

Args:

    channel_: 频道

    data: 数据



Returns:

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `on_subscriber_receive(self, channel_: str) -> Callable[[ON_RECEIVE_FUNC], ON_RECEIVE_FUNC]`

&emsp;订阅者接收消息时的回调

Args:

    channel_: 频道



Returns:

    装饰器

<details>
<summary>源代码</summary>

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

### &emsp; ***@staticmethod***
### &emsp; ***def*** `run_subscriber_receive_funcs(channel_: str, data: Any) -> None`

&emsp;运行订阅者接收函数

Args:

    channel_: 频道

    data: 数据

<details>
<summary>源代码</summary>

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
            run_coroutine(*[func(data) for func in _on_main_subscriber_receive_funcs[channel_]])
    elif channel_ in _on_sub_subscriber_receive_funcs and _on_sub_subscriber_receive_funcs[channel_]:
        run_coroutine(*[func(data) for func in _on_sub_subscriber_receive_funcs[channel_]])
```
</details>

### ***class*** `GlobalKeyValueStore`



### &emsp; ***@classmethod***
### &emsp; ***def*** `get_instance(cls: Any) -> None`

&emsp;

<details>
<summary>源代码</summary>

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

### &emsp; ***attr*** `_instance: None`

### &emsp; ***attr*** `_lock: threading.Lock()`

### ***var*** `key = data[1]['key']`



### ***var*** `default = data[1]['default']`



### ***var*** `recv_chan = data[1]['recv_chan']`



### ***var*** `key = data[1]['key']`



### ***var*** `value = data[1]['value']`



### ***var*** `key = data[1]['key']`



### ***var*** `recv_chan = data[1]['recv_chan']`



### ***var*** `lock = _get_lock(key)`



### ***var*** `lock = _get_lock(key)`



### ***var*** `recv_chan = Channel[Optional[Any]]('recv_chan')`



### ***var*** `lock = _get_lock(key)`



### ***var*** `recv_chan = Channel[dict[str, Any]]('recv_chan')`



### ***var*** `data = self.active_chan.receive()`



### ***var*** `data = self.publish_channel.receive()`



