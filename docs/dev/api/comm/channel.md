---
title: liteyuki.comm.channel
---
### *func* `set_channel()`



**说明**: 设置通道实例

**参数**:
> - name: 通道名称  
> - channel: 通道实例  


<details>
<summary> <b>源代码</b> </summary>

```python
def set_channel(name: str, channel: Channel):
    """
    设置通道实例
    Args:
        name: 通道名称
        channel: 通道实例
    """
    if not isinstance(channel, Channel):
        raise TypeError(f'channel_ must be an instance of Channel, {type(channel)} found')
    if IS_MAIN_PROCESS:
        _channel[name] = channel
    else:
        channel_deliver_passive_channel.send(('set_channel', {'name': name, 'channel_': channel}))
```
</details>

### *func* `set_channels()`



**说明**: 设置通道实例

**参数**:
> - channels: 通道名称  


<details>
<summary> <b>源代码</b> </summary>

```python
def set_channels(channels: dict[str, Channel]):
    """
    设置通道实例
    Args:
        channels: 通道名称
    """
    for name, channel in channels.items():
        set_channel(name, channel)
```
</details>

### *func* `get_channel() -> Channel`



**说明**: 获取通道实例

**参数**:
> - name: 通道名称  


<details>
<summary> <b>源代码</b> </summary>

```python
def get_channel(name: str) -> Channel:
    """
    获取通道实例
    Args:
        name: 通道名称
    Returns:
    """
    if IS_MAIN_PROCESS:
        return _channel[name]
    else:
        recv_chan = Channel[Channel[Any]]('recv_chan')
        channel_deliver_passive_channel.send(('get_channel', {'name': name, 'recv_chan': recv_chan}))
        return recv_chan.receive()
```
</details>

### *func* `get_channels() -> dict[str, Channel]`



**说明**: 获取通道实例


<details>
<summary> <b>源代码</b> </summary>

```python
def get_channels() -> dict[str, Channel]:
    """
    获取通道实例
    Returns:
    """
    if IS_MAIN_PROCESS:
        return _channel
    else:
        recv_chan = Channel[dict[str, Channel[Any]]]('recv_chan')
        channel_deliver_passive_channel.send(('get_channels', {'recv_chan': recv_chan}))
        return recv_chan.receive()
```
</details>

### `@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'set_channel')`
### *func* `on_set_channel()`


<details>
<summary> <b>源代码</b> </summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'set_channel')
def on_set_channel(data: tuple[str, dict[str, Any]]):
    name, channel = (data[1]['name'], data[1]['channel_'])
    set_channel(name, channel)
```
</details>

### `@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channel')`
### *func* `on_get_channel()`


<details>
<summary> <b>源代码</b> </summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channel')
def on_get_channel(data: tuple[str, dict[str, Any]]):
    name, recv_chan = (data[1]['name'], data[1]['recv_chan'])
    recv_chan.send(get_channel(name))
```
</details>

### `@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channels')`
### *func* `on_get_channels()`


<details>
<summary> <b>源代码</b> </summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channels')
def on_get_channels(data: tuple[str, dict[str, Any]]):
    recv_chan = data[1]['recv_chan']
    recv_chan.send(get_channels())
```
</details>

### **class** `Channel(Generic[T])`
### *method* `__init__(self, _id: str = '', type_check: Optional[bool] = None)`



**说明**: 初始化通道

**参数**:
> - _id: 通道ID  
> - type_check: 是否开启类型检查, 若为空，则传入泛型默认开启，否则默认关闭  


<details>
<summary> <b>源代码</b> </summary>

```python
def __init__(self, _id: str='', type_check: Optional[bool]=None):
    """
        初始化通道
        Args:
            _id: 通道ID
            type_check: 是否开启类型检查, 若为空，则传入泛型默认开启，否则默认关闭
        """
    self.conn_send, self.conn_recv = Pipe()
    self._closed = False
    self._on_main_receive_funcs: list[int] = []
    self._on_sub_receive_funcs: list[int] = []
    self.name: str = _id
    self.is_main_receive_loop_running = False
    self.is_sub_receive_loop_running = False
    if type_check is None:
        type_check = self._get_generic_type() is not None
    elif type_check:
        if self._get_generic_type() is None:
            raise TypeError('Type hint is required for enforcing type check.')
    self.type_check = type_check
```
</details>

### *method* `_get_generic_type(self) -> Optional[type]`



**说明**: 获取通道传递泛型类型


**返回**: Optional[type]: 泛型类型


<details>
<summary> <b>源代码</b> </summary>

```python
def _get_generic_type(self) -> Optional[type]:
    """
        获取通道传递泛型类型

        Returns:
            Optional[type]: 泛型类型
        """
    if hasattr(self, '__orig_class__'):
        return get_args(self.__orig_class__)[0]
    return None
```
</details>

### *method* `_validate_structure(self, data: Any, structure: type) -> bool`



**说明**: 验证数据结构

**参数**:
> - data: 数据  
> - structure: 结构  

**返回**: bool: 是否通过验证


<details>
<summary> <b>源代码</b> </summary>

```python
def _validate_structure(self, data: Any, structure: type) -> bool:
    """
        验证数据结构
        Args:
            data: 数据
            structure: 结构

        Returns:
            bool: 是否通过验证
        """
    if isinstance(structure, type):
        return isinstance(data, structure)
    elif isinstance(structure, tuple):
        if not isinstance(data, tuple) or len(data) != len(structure):
            return False
        return all((self._validate_structure(d, s) for d, s in zip(data, structure)))
    elif isinstance(structure, list):
        if not isinstance(data, list):
            return False
        return all((self._validate_structure(d, structure[0]) for d in data))
    elif isinstance(structure, dict):
        if not isinstance(data, dict):
            return False
        return all((k in data and self._validate_structure(data[k], structure[k]) for k in structure))
    return False
```
</details>

### *method* `send(self, data: T)`



**说明**: 发送数据

**参数**:
> - data: 数据  


<details>
<summary> <b>源代码</b> </summary>

```python
def send(self, data: T):
    """
        发送数据
        Args:
            data: 数据
        """
    if self.type_check:
        _type = self._get_generic_type()
        if _type is not None and (not self._validate_structure(data, _type)):
            raise TypeError(f'Data must be an instance of {_type}, {type(data)} found')
    if self._closed:
        raise RuntimeError('Cannot send to a closed channel_')
    self.conn_send.send(data)
```
</details>

### *method* `receive(self) -> T`



**说明**: 接收数据


<details>
<summary> <b>源代码</b> </summary>

```python
def receive(self) -> T:
    """
        接收数据
        Args:
        """
    if self._closed:
        raise RuntimeError('Cannot receive from a closed channel_')
    while True:
        data = self.conn_recv.recv()
        return data
```
</details>

### *method* `close(self)`



**说明**: 关闭通道


<details>
<summary> <b>源代码</b> </summary>

```python
def close(self):
    """
        关闭通道
        """
    self._closed = True
    self.conn_send.close()
    self.conn_recv.close()
```
</details>

### *method* `on_receive(self, filter_func: Optional[FILTER_FUNC] = None) -> Callable[[Callable[[T], Any]], Callable[[T], Any]]`



**说明**: 接收数据并执行函数

**参数**:
> - filter_func: 过滤函数，为None则不过滤  

**返回**: 装饰器，装饰一个函数在接收到数据后执行


<details>
<summary> <b>源代码</b> </summary>

```python
def on_receive(self, filter_func: Optional[FILTER_FUNC]=None) -> Callable[[Callable[[T], Any]], Callable[[T], Any]]:
    """
        接收数据并执行函数
        Args:
            filter_func: 过滤函数，为None则不过滤
        Returns:
            装饰器，装饰一个函数在接收到数据后执行
        """
    if not self.is_sub_receive_loop_running and (not IS_MAIN_PROCESS):
        threading.Thread(target=self._start_sub_receive_loop, daemon=True).start()
    if not self.is_main_receive_loop_running and IS_MAIN_PROCESS:
        threading.Thread(target=self._start_main_receive_loop, daemon=True).start()

    def decorator(func: Callable[[T], Any]) -> Callable[[T], Any]:
        global _func_id

        async def wrapper(data: T) -> Any:
            if filter_func is not None:
                if is_coroutine_callable(filter_func):
                    if not await filter_func(data):
                        return
                elif not filter_func(data):
                    return
            if is_coroutine_callable(func):
                return await func(data)
            else:
                return func(data)
        _callback_funcs[_func_id] = wrapper
        if IS_MAIN_PROCESS:
            self._on_main_receive_funcs.append(_func_id)
        else:
            self._on_sub_receive_funcs.append(_func_id)
        _func_id += 1
        return func
    return decorator
```
</details>

### *method* `_run_on_main_receive_funcs(self, data: Any)`



**说明**: 运行接收函数

**参数**:
> - data: 数据  


<details>
<summary> <b>源代码</b> </summary>

```python
def _run_on_main_receive_funcs(self, data: Any):
    """
        运行接收函数
        Args:
            data: 数据
        """
    for func_id in self._on_main_receive_funcs:
        func = _callback_funcs[func_id]
        run_coroutine(func(data))
```
</details>

### *method* `_run_on_sub_receive_funcs(self, data: Any)`



**说明**: 运行接收函数

**参数**:
> - data: 数据  


<details>
<summary> <b>源代码</b> </summary>

```python
def _run_on_sub_receive_funcs(self, data: Any):
    """
        运行接收函数
        Args:
            data: 数据
        """
    for func_id in self._on_sub_receive_funcs:
        func = _callback_funcs[func_id]
        run_coroutine(func(data))
```
</details>

### *method* `_start_main_receive_loop(self)`



**说明**: 开始接收数据


<details>
<summary> <b>源代码</b> </summary>

```python
def _start_main_receive_loop(self):
    """
        开始接收数据
        """
    self.is_main_receive_loop_running = True
    while not self._closed:
        data = self.conn_recv.recv()
        self._run_on_main_receive_funcs(data)
```
</details>

### *method* `_start_sub_receive_loop(self)`



**说明**: 开始接收数据


<details>
<summary> <b>源代码</b> </summary>

```python
def _start_sub_receive_loop(self):
    """
        开始接收数据
        """
    self.is_sub_receive_loop_running = True
    while not self._closed:
        data = self.conn_recv.recv()
        self._run_on_sub_receive_funcs(data)
```
</details>

### ***var*** `SYNC_ON_RECEIVE_FUNC = Callable[[T], Any]`

- **类型**: `TypeAlias`

### ***var*** `ASYNC_ON_RECEIVE_FUNC = Callable[[T], Coroutine[Any, Any, Any]]`

- **类型**: `TypeAlias`

### ***var*** `ON_RECEIVE_FUNC = SYNC_ON_RECEIVE_FUNC | ASYNC_ON_RECEIVE_FUNC`

- **类型**: `TypeAlias`

### ***var*** `SYNC_FILTER_FUNC = Callable[[T], bool]`

- **类型**: `TypeAlias`

### ***var*** `ASYNC_FILTER_FUNC = Callable[[T], Coroutine[Any, Any, bool]]`

- **类型**: `TypeAlias`

### ***var*** `FILTER_FUNC = SYNC_FILTER_FUNC | ASYNC_FILTER_FUNC`

- **类型**: `TypeAlias`

### ***var*** `_func_id = 0`

- **类型**: `int`

### ***var*** `_channel = {}`

- **类型**: `dict[str, 'Channel']`

### ***var*** `_callback_funcs = {}`

- **类型**: `dict[int, ON_RECEIVE_FUNC]`

### ***var*** `active_channel = None`

- **类型**: `Optional['Channel']`

- **说明**: 子进程可用的主动和被动通道

### ***var*** `passive_channel = None`

- **类型**: `Optional['Channel']`

### ***var*** `publish_channel = Channel(_id='publish_channel')`

- **类型**: `Channel[tuple[str, dict[str, Any]]]`

### ***var*** `channel_deliver_active_channel = NO_DEFAULT`

- **类型**: `Channel[Channel[Any]]`

- **说明**: 通道传递通道，主进程创建单例，子进程初始化时实例化

### ***var*** `channel_deliver_passive_channel = NO_DEFAULT`

- **类型**: `Channel[tuple[str, dict[str, Any]]]`

