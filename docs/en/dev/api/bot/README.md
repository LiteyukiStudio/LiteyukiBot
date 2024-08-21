---
title: liteyuki.bot
index: true
icon: laptop-code
category: API
---

### ***def*** `get_bot() -> LiteyukiBot`

获取轻雪实例



Returns:

    LiteyukiBot: 当前的轻雪实例

<details>
<summary>源代码</summary>

```python
def get_bot() -> LiteyukiBot:
    """
    获取轻雪实例

    Returns:
        LiteyukiBot: 当前的轻雪实例
    """
    if IS_MAIN_PROCESS:
        if _BOT_INSTANCE is None:
            raise RuntimeError('Liteyuki instance not initialized.')
        return _BOT_INSTANCE
    else:
        raise RuntimeError("Can't get bot instance in sub process.")
```
</details>

### ***def*** `get_config(key: str, default: Any) -> Any`

获取配置

Args:

    key: 配置键

    default: 默认值



Returns:

    Any: 配置值

<details>
<summary>源代码</summary>

```python
def get_config(key: str, default: Any=None) -> Any:
    """
    获取配置
    Args:
        key: 配置键
        default: 默认值

    Returns:
        Any: 配置值
    """
    return get_bot().config.get(key, default)
```
</details>

### ***def*** `get_config_with_compat(key: str, compat_keys: tuple[str], default: Any) -> Any`

获取配置，兼容旧版本

Args:

    key: 配置键

    compat_keys: 兼容键

    default: 默认值



Returns:

    Any: 配置值

<details>
<summary>源代码</summary>

```python
def get_config_with_compat(key: str, compat_keys: tuple[str], default: Any=None) -> Any:
    """
    获取配置，兼容旧版本
    Args:
        key: 配置键
        compat_keys: 兼容键
        default: 默认值

    Returns:
        Any: 配置值
    """
    if key in get_bot().config:
        return get_bot().config[key]
    for compat_key in compat_keys:
        if compat_key in get_bot().config:
            logger.warning(f'Config key "{compat_key}" will be deprecated, use "{key}" instead.')
            return get_bot().config[compat_key]
    return default
```
</details>

### ***def*** `print_logo() -> None`



<details>
<summary>源代码</summary>

```python
def print_logo():
    print('\x1b[34m' + '\n     __        ______  ________  ________  __      __  __    __  __    __  ______ \n    /  |      /      |/        |/        |/  \\    /  |/  |  /  |/  |  /  |/      |\n    $$ |      $$$$$$/ $$$$$$$$/ $$$$$$$$/ $$  \\  /$$/ $$ |  $$ |$$ | /$$/ $$$$$$/ \n    $$ |        $$ |     $$ |   $$ |__     $$  \\/$$/  $$ |  $$ |$$ |/$$/    $$ |  \n    $$ |        $$ |     $$ |   $$    |     $$  $$/   $$ |  $$ |$$  $$<     $$ |  \n    $$ |        $$ |     $$ |   $$$$$/       $$$$/    $$ |  $$ |$$$$$  \\    $$ |  \n    $$ |_____  _$$ |_    $$ |   $$ |_____     $$ |    $$ \\__$$ |$$ |$$  \\  _$$ |_ \n    $$       |/ $$   |   $$ |   $$       |    $$ |    $$    $$/ $$ | $$  |/ $$   |\n    $$$$$$$$/ $$$$$$/    $$/    $$$$$$$$/     $$/      $$$$$$/  $$/   $$/ $$$$$$/ \n                ' + '\x1b[0m')
```
</details>

### ***class*** `LiteyukiBot`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;初始化轻雪实例

Args:

    *args:

    **kwargs: 配置

<details>
<summary>源代码</summary>

```python
def __init__(self, *args, **kwargs) -> None:
    """
        初始化轻雪实例
        Args:
            *args:
            **kwargs: 配置

        """
    '常规操作'
    print_logo()
    global _BOT_INSTANCE
    _BOT_INSTANCE = self
    '配置'
    self.config: dict[str, Any] = kwargs
    '初始化'
    self.init(**self.config)
    logger.info('Liteyuki is initializing...')
    '生命周期管理'
    self.lifespan = Lifespan()
    self.process_manager: ProcessManager = ProcessManager(lifespan=self.lifespan)
    '事件循环'
    self.loop = asyncio.new_event_loop()
    asyncio.set_event_loop(self.loop)
    self.stop_event = threading.Event()
    self.call_restart_count = 0
    '加载插件加载器'
    load_plugin('liteyuki.plugins.plugin_loader')
    '信号处理'
    signal.signal(signal.SIGINT, self._handle_exit)
    signal.signal(signal.SIGTERM, self._handle_exit)
    atexit.register(self.process_manager.terminate_all)
```
</details>

### &emsp; ***def*** `run(self) -> None`

&emsp;启动逻辑

<details>
<summary>源代码</summary>

```python
def run(self):
    """
        启动逻辑
        """
    self.lifespan.before_start()
    self.process_manager.start_all()
    self.lifespan.after_start()
    self.keep_alive()
```
</details>

### &emsp; ***def*** `keep_alive(self) -> None`

&emsp;保持轻雪运行

Returns:

<details>
<summary>源代码</summary>

```python
def keep_alive(self):
    """
        保持轻雪运行
        Returns:

        """
    try:
        while not self.stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info('Liteyuki is stopping...')
        self.stop()
```
</details>

### &emsp; ***def*** `restart(self, delay: int) -> None`

&emsp;重启轻雪本体

Returns:

<details>
<summary>源代码</summary>

```python
def restart(self, delay: int=0):
    """
        重启轻雪本体
        Returns:

        """
    if self.call_restart_count < 1:
        executable = sys.executable
        args = sys.argv
        logger.info('Restarting LiteyukiBot...')
        time.sleep(delay)
        if platform.system() == 'Windows':
            cmd = 'start'
        elif platform.system() == 'Linux':
            cmd = 'nohup'
        elif platform.system() == 'Darwin':
            cmd = 'open'
        else:
            cmd = 'nohup'
        self.process_manager.terminate_all()
        threading.Thread(target=os.system, args=(f"{cmd} {executable} {' '.join(args)}",)).start()
        sys.exit(0)
    self.call_restart_count += 1
```
</details>

### &emsp; ***def*** `restart_process(self, name: Optional[str]) -> None`

&emsp;停止轻雪

Args:

    name: 进程名称, 默认为None, 所有进程

Returns:

<details>
<summary>源代码</summary>

```python
def restart_process(self, name: Optional[str]=None):
    """
        停止轻雪
        Args:
            name: 进程名称, 默认为None, 所有进程
        Returns:
        """
    self.lifespan.before_process_shutdown()
    self.lifespan.before_process_shutdown()
    if name is not None:
        chan_active = get_channel(f'{name}-active')
        chan_active.send(1)
    else:
        for process_name in self.process_manager.processes:
            chan_active = get_channel(f'{process_name}-active')
            chan_active.send(1)
```
</details>

### &emsp; ***def*** `init(self) -> None`

&emsp;初始化轻雪, 自动调用

Returns:

<details>
<summary>源代码</summary>

```python
def init(self, *args, **kwargs):
    """
        初始化轻雪, 自动调用
        Returns:

        """
    self.init_logger()
```
</details>

### &emsp; ***def*** `init_logger(self) -> None`

&emsp;

<details>
<summary>源代码</summary>

```python
def init_logger(self):
    init_log(config=self.config)
```
</details>

### &emsp; ***def*** `stop(self) -> None`

&emsp;停止轻雪

Returns:

<details>
<summary>源代码</summary>

```python
def stop(self):
    """
        停止轻雪
        Returns:

        """
    self.stop_event.set()
    self.loop.stop()
```
</details>

### &emsp; ***def*** `on_before_start(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动前的函数

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_before_start(self, func: LIFESPAN_FUNC):
    """
        注册启动前的函数
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_before_start(func)
```
</details>

### &emsp; ***def*** `on_after_start(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动后的函数

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_after_start(self, func: LIFESPAN_FUNC):
    """
        注册启动后的函数
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_after_start(func)
```
</details>

### &emsp; ***def*** `on_after_shutdown(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册停止后的函数：未实现

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_after_shutdown(self, func: LIFESPAN_FUNC):
    """
        注册停止后的函数：未实现
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_after_shutdown(func)
```
</details>

### &emsp; ***def*** `on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程停止前的函数，为子进程停止时调用

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_before_process_shutdown(self, func: LIFESPAN_FUNC):
    """
        注册进程停止前的函数，为子进程停止时调用
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_before_process_shutdown(func)
```
</details>

### &emsp; ***def*** `on_before_process_restart(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程重启前的函数，为子进程重启时调用

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_before_process_restart(self, func: LIFESPAN_FUNC):
    """
        注册进程重启前的函数，为子进程重启时调用
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_before_process_restart(func)
```
</details>

### &emsp; ***def*** `on_after_restart(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册重启后的函数：未实现

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_after_restart(self, func: LIFESPAN_FUNC):
    """
        注册重启后的函数：未实现
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_after_restart(func)
```
</details>

### &emsp; ***def*** `on_after_nonebot_init(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册nonebot初始化后的函数

Args:

    func:



Returns:

<details>
<summary>源代码</summary>

```python
def on_after_nonebot_init(self, func: LIFESPAN_FUNC):
    """
        注册nonebot初始化后的函数
        Args:
            func:

        Returns:

        """
    return self.lifespan.on_after_nonebot_init(func)
```
</details>

### ***var*** `executable = sys.executable`



### ***var*** `args = sys.argv`



### ***var*** `chan_active = get_channel(f'{name}-active')`



### ***var*** `cmd = 'start'`



### ***var*** `chan_active = get_channel(f'{process_name}-active')`



### ***var*** `cmd = 'nohup'`



### ***var*** `cmd = 'open'`



### ***var*** `cmd = 'nohup'`



