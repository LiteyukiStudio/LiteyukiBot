---
title: liteyuki.comm.channel
order: 1
icon: laptop-code
category: API
---

### ***def*** `set_channel(name: str, channel: Channel) -> None`

设置通道实例

Args:

    name: 通道名称

    channel: 通道实例

<details>
<summary>源代码</summary>

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

### ***def*** `set_channels(channels: dict[str, Channel]) -> None`

设置通道实例

Args:

    channels: 通道名称

<details>
<summary>源代码</summary>

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

### ***def*** `get_channel(name: str) -> Channel`

获取通道实例

Args:

    name: 通道名称

Returns:

<details>
<summary>源代码</summary>

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

### ***def*** `get_channels() -> dict[str, Channel]`

获取通道实例

Returns:

<details>
<summary>源代码</summary>

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

### ***def*** `on_set_channel(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'set_channel')
def on_set_channel(data: tuple[str, dict[str, Any]]):
    name, channel = (data[1]['name'], data[1]['channel_'])
    set_channel(name, channel)
```
</details>

### ***def*** `on_get_channel(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channel')
def on_get_channel(data: tuple[str, dict[str, Any]]):
    name, recv_chan = (data[1]['name'], data[1]['recv_chan'])
    recv_chan.send(get_channel(name))
```
</details>

### ***def*** `on_get_channels(data: tuple[str, dict[str, Any]]) -> None`



<details>
<summary>源代码</summary>

```python
@channel_deliver_passive_channel.on_receive(filter_func=lambda data: data[0] == 'get_channels')
def on_get_channels(data: tuple[str, dict[str, Any]]):
    recv_chan = data[1]['recv_chan']
    recv_chan.send(get_channels())
```
</details>

### ***def*** `decorator(func: Callable[[T], Any]) -> Callable[[T], Any]`



<details>
<summary>源代码</summary>

```python
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
```
</details>

### ***async def*** `wrapper(data: T) -> Any`



<details>
<summary>源代码</summary>

```python
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
```
</details>

### ***class*** `Channel(Generic[T])`

通道类，可以在进程间和进程内通信，双向但同时只能有一个发送者和一个接收者

有两种接收工作方式，但是只能选择一种，主动接收和被动接收，主动接收使用 `receive` 方法，被动接收使用 `on_receive` 装饰器

### &emsp; ***def*** `__init__(self, _id: str, type_check: Optional[bool]) -> None`

&emsp;初始化通道

Args:

    _id: 通道ID

    type_check: 是否开启类型检查, 若为空，则传入泛型默认开启，否则默认关闭

<details>
<summary>源代码</summary>

```python
def __init__(self, _id: str, type_check: Optional[bool]=None):
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

### &emsp; ***def*** `send(self, data: T) -> None`

&emsp;发送数据

Args:

    data: 数据

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `receive(self) -> T`

&emsp;接收数据

Args:

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `close(self) -> None`

&emsp;关闭通道

<details>
<summary>源代码</summary>

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

### &emsp; ***def*** `on_receive(self, filter_func: Optional[FILTER_FUNC]) -> Callable[[Callable[[T], Any]], Callable[[T], Any]]`

&emsp;接收数据并执行函数

Args:

    filter_func: 过滤函数，为None则不过滤

Returns:

    装饰器，装饰一个函数在接收到数据后执行

<details>
<summary>源代码</summary>

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

### ***var*** `T = TypeVar('T')`



### ***var*** `channel_deliver_active_channel = Channel(_id='channel_deliver_active_channel')`



### ***var*** `channel_deliver_passive_channel = Channel(_id='channel_deliver_passive_channel')`



### ***var*** `recv_chan = data[1]['recv_chan']`



### ***var*** `recv_chan = Channel[Channel[Any]]('recv_chan')`



### ***var*** `recv_chan = Channel[dict[str, Channel[Any]]]('recv_chan')`



### ***var*** `type_check = self._get_generic_type() is not None`



### ***var*** `data = self.conn_recv.recv()`



### ***var*** `func = _callback_funcs[func_id]`



### ***var*** `func = _callback_funcs[func_id]`



### ***var*** `data = self.conn_recv.recv()`



### ***var*** `data = self.conn_recv.recv()`



