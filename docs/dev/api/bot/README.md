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

### ***def*** `get_config(key: str, default: Any) -> Any`

获取配置

Args:

    key: 配置键

    default: 默认值



Returns:

    Any: 配置值

### ***def*** `get_config_with_compat(key: str, compat_keys: tuple[str], default: Any) -> Any`

获取配置，兼容旧版本

Args:

    key: 配置键

    compat_keys: 兼容键

    default: 默认值



Returns:

    Any: 配置值

### ***def*** `print_logo() -> None`



### ***class*** `LiteyukiBot`



### &emsp; ***def*** `__init__(self) -> None`

&emsp;初始化轻雪实例

Args:

    *args:

    **kwargs: 配置

### &emsp; ***def*** `run(self) -> None`

&emsp;启动逻辑

### &emsp; ***def*** `keep_alive(self) -> None`

&emsp;保持轻雪运行

Returns:

### &emsp; ***def*** `restart(self, delay: int) -> None`

&emsp;重启轻雪本体

Returns:

### &emsp; ***def*** `restart_process(self, name: Optional[str]) -> None`

&emsp;停止轻雪

Args:

    name: 进程名称, 默认为None, 所有进程

Returns:

### &emsp; ***def*** `init(self) -> None`

&emsp;初始化轻雪, 自动调用

Returns:

### &emsp; ***def*** `init_logger(self) -> None`

&emsp;

### &emsp; ***def*** `stop(self) -> None`

&emsp;停止轻雪

Returns:

### &emsp; ***def*** `on_before_start(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动前的函数

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_start(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册启动后的函数

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_shutdown(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册停止后的函数：未实现

Args:

    func:



Returns:

### &emsp; ***def*** `on_before_process_shutdown(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程停止前的函数，为子进程停止时调用

Args:

    func:



Returns:

### &emsp; ***def*** `on_before_process_restart(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册进程重启前的函数，为子进程重启时调用

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_restart(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册重启后的函数：未实现

Args:

    func:



Returns:

### &emsp; ***def*** `on_after_nonebot_init(self, func: LIFESPAN_FUNC) -> None`

&emsp;注册nonebot初始化后的函数

Args:

    func:



Returns:

### ***var*** `executable = sys.executable`



### ***var*** `args = sys.argv`



### ***var*** `chan_active = get_channel(f'{name}-active')`



### ***var*** `cmd = 'start'`



### ***var*** `chan_active = get_channel(f'{process_name}-active')`



### ***var*** `cmd = 'nohup'`



### ***var*** `cmd = 'open'`



### ***var*** `cmd = 'nohup'`



